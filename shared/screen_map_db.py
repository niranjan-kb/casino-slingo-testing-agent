"""
Persistent screen-element coordinate database.

Stores per-device, per-screen element coordinates with confidence tracking.
Supports cross-device fallback (use closest resolution when current device has no data).
Records observations for debugging and learning.
"""

import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# Default DB path — sits alongside docker volumes in data/
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "screen_map.db")


class ScreenMapDB:
    """Thread-safe SQLite wrapper for screen element coordinate storage."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    # ── Device Profiles ──────────────────────────────────────────────

    def ensure_device_profile(
        self,
        device_name: str,
        resolution: str,
        platform: str = "android",
        density_dpi: Optional[int] = None,
    ) -> str:
        """Create or return existing device profile. Returns profile ID."""
        profile_id = f"{device_name}:{resolution}"
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO device_profiles (id, device_name, resolution, platform, density_dpi)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET density_dpi = COALESCE(excluded.density_dpi, density_dpi)""",
            (profile_id, device_name, resolution, platform, density_dpi),
        )
        conn.commit()
        return profile_id

    def list_device_profiles(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM device_profiles ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ── Element Coordinates (the core lookup) ────────────────────────

    def get_element_coords(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
        element_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Look up coordinates for a specific element on a specific device.

        Returns dict with x, y, confidence, source, etc. or None.
        """
        conn = self._get_conn()
        row = conn.execute(
            """SELECT * FROM screen_elements
               WHERE device_profile_id = ? AND app_context = ? AND screen_name = ? AND element_name = ?""",
            (device_profile_id, app_context, screen_name, element_name),
        ).fetchone()
        return dict(row) if row else None

    def get_best_guess_coords(
        self,
        app_context: str,
        screen_name: str,
        element_name: str,
        target_resolution: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Cross-device fallback: find this element on ANY device, prefer closest resolution.

        Used when current device has no data for this element.
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT se.*, dp.resolution FROM screen_elements se
               JOIN device_profiles dp ON se.device_profile_id = dp.id
               WHERE se.app_context = ? AND se.screen_name = ? AND se.element_name = ?
               ORDER BY se.confidence DESC, se.times_succeeded DESC""",
            (app_context, screen_name, element_name),
        ).fetchall()

        if not rows:
            return None

        # If we have a target resolution, prefer exact match
        if target_resolution:
            for row in rows:
                if row["resolution"] == target_resolution:
                    result = dict(row)
                    result["cross_device"] = True
                    return result

        # Otherwise return highest confidence
        result = dict(rows[0])
        result["cross_device"] = True
        return result

    def get_all_elements_for_screen(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
    ) -> List[Dict[str, Any]]:
        """Get all known elements for a screen on a device."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM screen_elements
               WHERE device_profile_id = ? AND app_context = ? AND screen_name = ?
               ORDER BY element_name""",
            (device_profile_id, app_context, screen_name),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Element Upsert & Updates ─────────────────────────────────────

    def upsert_element(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
        element_name: str,
        x: int,
        y: int,
        source: str = "seed",
        element_type: Optional[str] = None,
        intent: Optional[str] = None,
        confidence: float = 0.5,
    ) -> None:
        """Insert or update an element's coordinates."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO screen_elements
                   (device_profile_id, app_context, screen_name, element_name, x, y,
                    element_type, intent, confidence, source, last_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(device_profile_id, app_context, screen_name, element_name)
               DO UPDATE SET
                   x = excluded.x,
                   y = excluded.y,
                   element_type = COALESCE(excluded.element_type, element_type),
                   intent = COALESCE(excluded.intent, intent),
                   confidence = excluded.confidence,
                   source = excluded.source,
                   last_verified = excluded.last_verified""",
            (device_profile_id, app_context, screen_name, element_name, x, y,
             element_type, intent, confidence, source, datetime.utcnow().isoformat()),
        )
        conn.commit()

    def record_tap_result(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
        element_name: str,
        success: bool,
    ) -> None:
        """Record whether a tap on cached coordinates succeeded.

        Updates times_used, times_succeeded, and recalculates confidence.
        """
        conn = self._get_conn()
        conn.execute(
            """UPDATE screen_elements
               SET times_used = times_used + 1,
                   times_succeeded = times_succeeded + ?,
                   confidence = CAST(times_succeeded + ? AS REAL) / (times_used + 1),
                   last_verified = ?
               WHERE device_profile_id = ? AND app_context = ? AND screen_name = ? AND element_name = ?""",
            (int(success), int(success), datetime.utcnow().isoformat(),
             device_profile_id, app_context, screen_name, element_name),
        )
        conn.commit()

    def correct_element_coords(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
        element_name: str,
        new_x: int,
        new_y: int,
        source: str = "vision",
    ) -> None:
        """Correct coordinates after a failed tap. Resets confidence tracking."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE screen_elements
               SET x = ?, y = ?, source = ?,
                   confidence = 0.6,
                   times_used = 0, times_succeeded = 0,
                   last_verified = ?
               WHERE device_profile_id = ? AND app_context = ? AND screen_name = ? AND element_name = ?""",
            (new_x, new_y, source, datetime.utcnow().isoformat(),
             device_profile_id, app_context, screen_name, element_name),
        )
        # If row didn't exist, insert it
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            self.upsert_element(
                device_profile_id, app_context, screen_name, element_name,
                new_x, new_y, source=source, confidence=0.6,
            )
        conn.commit()

    # ── Screen Signatures (for element-based screen detection) ───────

    def get_screen_signatures(
        self, app_context: str = "platform"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get all screen signatures grouped by screen_name.

        Returns: {"login": [{"type": "element_text", "value": "Sign In", ...}], ...}
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM screen_signatures
               WHERE app_context = ?
               ORDER BY screen_name, priority DESC""",
            (app_context,),
        ).fetchall()

        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            screen = row["screen_name"]
            if screen not in result:
                result[screen] = []
            result[screen].append(dict(row))
        return result

    def upsert_screen_signature(
        self,
        screen_name: str,
        app_context: str,
        signature_type: str,
        signature_value: str,
        priority: int = 0,
    ) -> None:
        """Add or update a screen signature for detection."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO screen_signatures (screen_name, app_context, signature_type, signature_value, priority)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(screen_name, app_context, signature_type, signature_value)
               DO UPDATE SET priority = excluded.priority""",
            (screen_name, app_context, signature_type, signature_value, priority),
        )
        conn.commit()

    # ── Run Observations (episodic memory) ───────────────────────────

    def log_observation(
        self,
        device_profile_id: str,
        screen_name: str,
        element_name: Optional[str] = None,
        action: Optional[str] = None,
        expected_result: Optional[str] = None,
        actual_result: Optional[str] = None,
        correction: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> int:
        """Log an observation from a run. Returns the observation ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO run_observations
                   (device_profile_id, screen_name, element_name, action,
                    expected_result, actual_result, correction, screenshot_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_profile_id, screen_name, element_name, action,
             expected_result, actual_result, correction, screenshot_path),
        )
        conn.commit()
        return cursor.lastrowid

    def get_recent_observations(
        self,
        device_profile_id: Optional[str] = None,
        screen_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent observations, optionally filtered."""
        conn = self._get_conn()
        query = "SELECT * FROM run_observations WHERE 1=1"
        params: list = []
        if device_profile_id:
            query += " AND device_profile_id = ?"
            params.append(device_profile_id)
        if screen_name:
            query += " AND screen_name = ?"
            params.append(screen_name)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_corrections_for_element(
        self,
        screen_name: str,
        element_name: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get recent corrections for a specific element across all devices."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM run_observations
               WHERE screen_name = ? AND element_name = ? AND correction IS NOT NULL
               ORDER BY timestamp DESC LIMIT ?""",
            (screen_name, element_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Utilities ────────────────────────────────────────────────────

    def get_low_confidence_elements(
        self,
        device_profile_id: str,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Find elements with low confidence that need verification."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM screen_elements
               WHERE device_profile_id = ? AND confidence <= ?
               ORDER BY confidence ASC""",
            (device_profile_id, threshold),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get DB stats for debugging."""
        conn = self._get_conn()
        return {
            "devices": conn.execute("SELECT COUNT(*) FROM device_profiles").fetchone()[0],
            "elements": conn.execute("SELECT COUNT(*) FROM screen_elements").fetchone()[0],
            "signatures": conn.execute("SELECT COUNT(*) FROM screen_signatures").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM run_observations").fetchone()[0],
        }

    def should_verify_tap(
        self,
        device_profile_id: str,
        app_context: str,
        screen_name: str,
        element_name: str,
    ) -> bool:
        """Determine whether a tap on this element still needs post-tap verification.

        Graduation policy (risk-tiered):
        - HIGH-RISK elements (money-related): always verify, no graduation
        - MEDIUM-RISK elements: graduate at 90% confidence AND >= 5 uses
        - LOW-RISK elements: graduate at 80% confidence AND >= 3 uses

        Returns True if verification is still needed.
        """
        elem = self.get_element_coords(device_profile_id, app_context, screen_name, element_name)
        if not elem:
            return True  # unknown element — always verify

        confidence = elem.get("confidence", 0)
        times_used = elem.get("times_used", 0)

        # HIGH-RISK: elements that can cost money or are irreversible
        # These NEVER graduate — always verify after tapping
        high_risk = {
            "spin_button",       # could trigger paid spin if game state misread
            "end_game_button",   # overlaps with spin_for — DANGER
            "stake_adjuster",    # changes bet amount
            "sign_in_button",    # auth flow — must confirm transition
            "otp_submit",        # auth flow
        }
        if element_name in high_risk:
            return True

        # MEDIUM-RISK: navigation elements where wrong tap wastes time
        medium_risk = {
            "close_button",      # exiting game prematurely = test failure
            "keep_playing",      # staying when we should exit
            "no_thanks_exit",    # exiting — must confirm
            "first_result",      # could tap wrong game
        }
        if element_name in medium_risk:
            return confidence < 0.9 or times_used < 5

        # LOW-RISK: everything else (search bar, grid cells, etc.)
        return confidence < 0.8 or times_used < 3

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# ── Schema DDL ───────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS device_profiles (
    id TEXT PRIMARY KEY,                        -- "Pixel_5_API_34:1080x1920"
    device_name TEXT NOT NULL,                  -- "Pixel_5_API_34"
    resolution TEXT NOT NULL,                   -- "1080x1920"
    platform TEXT NOT NULL DEFAULT 'android',
    density_dpi INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screen_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_profile_id TEXT NOT NULL,
    app_context TEXT NOT NULL DEFAULT 'platform',   -- 'platform' or 'slingo_cash_eruption'
    screen_name TEXT NOT NULL,                       -- 'login', 'home', 'main_game'
    element_name TEXT NOT NULL,                      -- 'search_bar', 'spin_button'
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    element_type TEXT,                               -- 'button', 'input', 'text', 'region'
    intent TEXT,                                     -- human-readable purpose
    confidence REAL DEFAULT 0.5,                     -- 0.0 to 1.0
    times_used INTEGER DEFAULT 0,
    times_succeeded INTEGER DEFAULT 0,
    last_verified TIMESTAMP,
    source TEXT DEFAULT 'seed',                      -- 'seed', 'vision', 'element', 'manual'
    FOREIGN KEY (device_profile_id) REFERENCES device_profiles(id),
    UNIQUE(device_profile_id, app_context, screen_name, element_name)
);

CREATE TABLE IF NOT EXISTS screen_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_name TEXT NOT NULL,
    app_context TEXT NOT NULL DEFAULT 'platform',
    signature_type TEXT NOT NULL,                    -- 'element_text', 'element_id', 'element_class'
    signature_value TEXT NOT NULL,
    priority INTEGER DEFAULT 0,                      -- higher = check first
    UNIQUE(screen_name, app_context, signature_type, signature_value)
);

CREATE TABLE IF NOT EXISTS run_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    device_profile_id TEXT,
    screen_name TEXT,
    element_name TEXT,
    action TEXT,                                      -- 'tap', 'type', 'find_element', 'screenshot'
    expected_result TEXT,
    actual_result TEXT,
    correction TEXT,
    screenshot_path TEXT,
    FOREIGN KEY (device_profile_id) REFERENCES device_profiles(id)
);

CREATE INDEX IF NOT EXISTS idx_elements_lookup
    ON screen_elements(device_profile_id, app_context, screen_name, element_name);

CREATE INDEX IF NOT EXISTS idx_elements_confidence
    ON screen_elements(device_profile_id, confidence);

CREATE INDEX IF NOT EXISTS idx_observations_device_screen
    ON run_observations(device_profile_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_signatures_screen
    ON screen_signatures(screen_name, app_context);
"""
