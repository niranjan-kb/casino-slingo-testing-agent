"""
Persistent screen-element coordinate database.

Stores per-device, per-screen element coordinates with confidence tracking.
Supports cross-device fallback (use closest resolution when current device has no data).
Records observations for debugging and learning.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# Default DB path — sits alongside docker volumes in data/
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "screen_map.db")


def _current_build_meta() -> Tuple[str, str]:
    """Read the worker's BUILD_ENV / APP_PACKAGE from the env at write time.

    Used to tag rows so read-time decay (screen_graph._effective_confidence)
    can downweight rows from a different build/package without destructively
    rewriting the stored confidence (MW-3).
    """
    return (
        os.getenv("BUILD_ENV", "unknown"),
        os.getenv("APP_PACKAGE", "unknown"),
    )


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
        self._ensure_build_columns(conn)
        self._ensure_spec_005_columns(conn)
        conn.commit()

    def _ensure_build_columns(self, conn: sqlite3.Connection) -> None:
        """Idempotent ALTER for the build_env / app_package columns added in feature 004."""
        for table in ("screen_signatures", "screen_elements", "screen_transitions"):
            cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "build_env" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN build_env TEXT DEFAULT 'unknown'")
            if "app_package" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN app_package TEXT DEFAULT 'unknown'")

    def _ensure_spec_005_columns(self, conn: sqlite3.Connection) -> None:
        """Idempotent ALTERs for spec 005 (Casino Game-Play & Verification Suite).

        Per data-model.md §7 (logical identity, parent_sig, dom_skeleton_hash, deprecated_at),
        §9 (signature_proposals clustering + status lifecycle), and FR-027 (auto-demote bookkeeping
        on screen_elements). All additions are non-destructive — existing rows get NULL/default.
        """
        sig_cols_to_add = (
            ("logical_id", "TEXT"),
            ("parent_sig", "TEXT"),
            ("deprecated_at", "TIMESTAMP"),
            ("dom_skeleton_hash", "TEXT"),
        )
        elem_cols_to_add = (
            ("logical_id", "TEXT"),
            ("risk_tier", "TEXT NOT NULL DEFAULT 'low'"),
            ("side_effect", "TEXT NOT NULL DEFAULT 'idempotent'"),
            ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
            ("needs_review", "INTEGER NOT NULL DEFAULT 0"),
        )
        proposals_cols_to_add = (
            ("dom_skeleton_hash", "TEXT"),
            ("cluster_id", "TEXT"),
            ("rejected_cooldown_until", "TIMESTAMP"),
            ("evidence_path", "TEXT"),
        )

        for table, additions in (
            ("screen_signatures", sig_cols_to_add),
            ("screen_elements", elem_cols_to_add),
            ("signature_proposals", proposals_cols_to_add),
        ):
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col_name, col_type in additions:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

        # SQL view for backward compatibility: legacy callers reading screen_transitions
        # still see the top-observed end_sig per (start_sig, action) from transition_outcomes.
        # The view name does NOT collide with the existing screen_transitions TABLE — we
        # expose it under transition_top_outcome instead so old code paths are unaffected
        # until they migrate explicitly.
        conn.execute(
            """CREATE VIEW IF NOT EXISTS transition_top_outcome AS
               SELECT start_sig, action, end_sig, observed_count, last_seen, edge_kind, side_effect, precondition
               FROM transition_outcomes o1
               WHERE observed_count = (
                   SELECT MAX(observed_count) FROM transition_outcomes o2
                   WHERE o2.start_sig = o1.start_sig AND o2.action = o1.action
               )"""
        )

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
        build_env, app_package = _current_build_meta()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO screen_elements
                   (device_profile_id, app_context, screen_name, element_name, x, y,
                    element_type, intent, confidence, source, last_verified,
                    build_env, app_package)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(device_profile_id, app_context, screen_name, element_name)
               DO UPDATE SET
                   x = excluded.x,
                   y = excluded.y,
                   element_type = COALESCE(excluded.element_type, element_type),
                   intent = COALESCE(excluded.intent, intent),
                   confidence = excluded.confidence,
                   source = excluded.source,
                   last_verified = excluded.last_verified,
                   build_env = excluded.build_env,
                   app_package = excluded.app_package""",
            (device_profile_id, app_context, screen_name, element_name, x, y,
             element_type, intent, confidence, source, datetime.utcnow().isoformat(),
             build_env, app_package),
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
            "transitions": conn.execute("SELECT COUNT(*) FROM screen_transitions").fetchone()[0],
            "games": conn.execute("SELECT COUNT(*) FROM game_catalog").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM run_observations").fetchone()[0],
            "observer_observations": conn.execute(
                "SELECT COUNT(*) FROM observation_log"
            ).fetchone()[0],
        }

    # ── Screen Transitions (the navigation graph) ────────────────────
    #
    # screen_transitions records "from screen A, doing X, lands on screen B".
    # Used by shared/screen_graph.py to plan paths between screens. Seeded
    # initially for known flows (login); populated by runtime observation
    # via record_transition_observation as the agent verifies new edges.

    def upsert_transition(
        self,
        from_screen: str,
        intent_verb: str,
        to_screen: str,
        *,
        intent_target: Optional[str] = None,
        intent_args: Optional[Dict[str, Any]] = None,
        app_context: str = "platform",
        confidence: float = 0.5,
        source: str = "seed",
    ) -> None:
        """Insert or update a transition row. Used by the seed script."""
        args_json = json.dumps(intent_args) if intent_args else None
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO screen_transitions
                   (from_screen, intent_verb, intent_target, intent_args_json,
                    to_screen, app_context, confidence, source, last_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(from_screen, intent_verb, intent_target, to_screen, app_context)
               DO UPDATE SET
                   confidence = excluded.confidence,
                   source = excluded.source,
                   intent_args_json = COALESCE(excluded.intent_args_json, intent_args_json),
                   last_verified = excluded.last_verified""",
            (from_screen, intent_verb, intent_target, args_json,
             to_screen, app_context, confidence, source,
             datetime.utcnow().isoformat()),
        )
        conn.commit()

    def record_transition_observation(
        self,
        from_screen: str,
        intent_verb: str,
        to_screen: str,
        *,
        intent_target: Optional[str] = None,
        intent_args: Optional[Dict[str, Any]] = None,
        success: bool = True,
        app_context: str = "platform",
    ) -> None:
        """Record a runtime observation of a transition. Bumps confidence on success."""
        args_json = json.dumps(intent_args) if intent_args else None
        build_env, app_package = _current_build_meta()
        conn = self._get_conn()
        # Ensure the row exists (zero-confidence floor for first-seen).
        conn.execute(
            """INSERT OR IGNORE INTO screen_transitions
                   (from_screen, intent_verb, intent_target, intent_args_json,
                    to_screen, app_context, confidence, source, last_verified,
                    build_env, app_package)
               VALUES (?, ?, ?, ?, ?, ?, 0.0, 'observed', ?, ?, ?)""",
            (from_screen, intent_verb, intent_target, args_json,
             to_screen, app_context, datetime.utcnow().isoformat(),
             build_env, app_package),
        )
        # SQLite needs the IS-NULL trick for the intent_target match; we
        # collapse it via COALESCE into a sentinel string for comparison.
        conn.execute(
            """UPDATE screen_transitions
               SET times_used = times_used + 1,
                   times_succeeded = times_succeeded + ?,
                   confidence = CAST(times_succeeded + ? AS REAL) / (times_used + 1),
                   last_verified = ?,
                   build_env = ?,
                   app_package = ?
               WHERE from_screen = ?
                 AND intent_verb = ?
                 AND COALESCE(intent_target, '') = COALESCE(?, '')
                 AND to_screen = ?
                 AND app_context = ?""",
            (int(success), int(success), datetime.utcnow().isoformat(),
             build_env, app_package,
             from_screen, intent_verb, intent_target, to_screen, app_context),
        )
        conn.commit()

    def get_transitions_from(
        self,
        from_screen: str,
        *,
        app_context: str = "platform",
    ) -> List[Dict[str, Any]]:
        """All known transitions out of a screen, ordered by confidence."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM screen_transitions
               WHERE from_screen = ? AND app_context = ?
               ORDER BY confidence DESC, times_succeeded DESC""",
            (from_screen, app_context),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_transitions_to(
        self,
        to_screen: str,
        *,
        app_context: str = "platform",
    ) -> List[Dict[str, Any]]:
        """All known transitions that LAND on a screen — useful for reverse-planning."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM screen_transitions
               WHERE to_screen = ? AND app_context = ?
               ORDER BY confidence DESC""",
            (to_screen, app_context),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Game Catalog (the agent's memory of games it has played) ─────

    def upsert_game(
        self,
        slug: str,
        name: str,
        *,
        category: Optional[str] = None,
        provider: Optional[str] = None,
        loaded_signature: Optional[str] = None,
        min_bet_usd: Optional[float] = None,
        max_bet_usd: Optional[float] = None,
        play_loop: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> None:
        play_loop_json = json.dumps(play_loop) if play_loop else None
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO game_catalog
                   (slug, name, category, provider, loaded_signature,
                    min_bet_usd, max_bet_usd, play_loop_json, last_seen, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                   name = COALESCE(excluded.name, name),
                   category = COALESCE(excluded.category, category),
                   provider = COALESCE(excluded.provider, provider),
                   loaded_signature = COALESCE(excluded.loaded_signature, loaded_signature),
                   min_bet_usd = COALESCE(excluded.min_bet_usd, min_bet_usd),
                   max_bet_usd = COALESCE(excluded.max_bet_usd, max_bet_usd),
                   play_loop_json = COALESCE(excluded.play_loop_json, play_loop_json),
                   last_seen = excluded.last_seen,
                   confidence = COALESCE(excluded.confidence, confidence)""",
            (slug, name, category, provider, loaded_signature,
             min_bet_usd, max_bet_usd, play_loop_json,
             datetime.utcnow().isoformat(), confidence),
        )
        conn.commit()

    def find_games(
        self,
        *,
        category: Optional[str] = None,
        name_like: Optional[str] = None,
        slug: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM game_catalog WHERE 1=1"
        params: list = []
        if slug:
            query += " AND slug = ?"
            params.append(slug)
        if category:
            query += " AND category = ?"
            params.append(category)
        if name_like:
            query += " AND name LIKE ?"
            params.append(f"%{name_like}%")
        query += " ORDER BY confidence DESC, last_seen DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ── Observer Framework Observations ──────────────────────────────
    #
    # observation_log is the durable ledger for the observer framework
    # (FR-018). Distinct from run_observations above, which records
    # per-tap diagnostic data. Each row is one ObservationResult emitted
    # by an observer engine; queryable by run_id, observer_id, severity.

    def log_observer_observation(
        self,
        observer_id: str,
        *,
        run_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        severity: str = "info",
        pass_fail: str = "n/a",
        matched: bool = False,
        auto_handle: bool = False,
        summary: Optional[str] = None,
        evidence_path: Optional[str] = None,
        spec_link: Optional[str] = None,
        failed_rule: Optional[str] = None,
        captured_json: Optional[str] = None,
        sub_flow_json: Optional[str] = None,
        screen_signature: Optional[str] = None,
        screen_id: Optional[str] = None,
    ) -> int:
        """Persist one ObservationResult. Returns new row id."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO observation_log
                   (run_id, goal_id, observer_id, severity, pass_fail, matched,
                    auto_handle, summary, evidence_path, spec_link, failed_rule,
                    captured_json, sub_flow_json, screen_signature, screen_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, goal_id, observer_id, severity, pass_fail, int(matched),
             int(auto_handle), summary, evidence_path, spec_link, failed_rule,
             captured_json, sub_flow_json, screen_signature, screen_id),
        )
        conn.commit()
        return cursor.lastrowid

    def get_recent_observer_observations(
        self,
        *,
        run_id: Optional[str] = None,
        observer_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Read observer-framework observations, optionally filtered."""
        conn = self._get_conn()
        query = "SELECT * FROM observation_log WHERE 1=1"
        params: list = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if observer_id:
            query += " AND observer_id = ?"
            params.append(observer_id)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

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

    # ── Signature Proposals (MW-4 / FR-021..023) ──────────────────────
    #
    # When the unknown-screen observer fires for the same `unk:<hash>`
    # signature ≥ 3 times across ≥ 2 distinct runs, scripts/scan_signature_proposals.py
    # upserts a row here so a human (or LLM-with-context) can review and
    # promote it into screen_signatures. Auto-promotion is forbidden.

    def upsert_signature_proposal(
        self,
        signature_hash: str,
        *,
        occurrence_count: int,
        distinct_runs: int,
        candidate_name: Optional[str] = None,
        top_text_signals: Optional[List[str]] = None,
        top_id_signals: Optional[List[str]] = None,
        last_seen_run_id: Optional[str] = None,
    ) -> int:
        """Insert a new pending proposal or refresh counts on an existing one.

        Returns the proposal id. Status is preserved on update — accepted /
        rejected proposals do not regress to pending if they re-fire.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO signature_proposals
                   (signature_hash, occurrence_count, distinct_runs,
                    candidate_name, top_text_signals_json, top_id_signals_json,
                    last_seen_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(signature_hash) DO UPDATE SET
                   occurrence_count = excluded.occurrence_count,
                   distinct_runs = excluded.distinct_runs,
                   candidate_name = COALESCE(excluded.candidate_name, candidate_name),
                   top_text_signals_json = COALESCE(excluded.top_text_signals_json, top_text_signals_json),
                   top_id_signals_json = COALESCE(excluded.top_id_signals_json, top_id_signals_json),
                   last_seen_run_id = COALESCE(excluded.last_seen_run_id, last_seen_run_id)""",
            (
                signature_hash, occurrence_count, distinct_runs, candidate_name,
                json.dumps(top_text_signals) if top_text_signals else None,
                json.dumps(top_id_signals) if top_id_signals else None,
                last_seen_run_id,
            ),
        )
        conn.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        row = conn.execute(
            "SELECT id FROM signature_proposals WHERE signature_hash = ?",
            (signature_hash,),
        ).fetchone()
        return int(row["id"]) if row else 0

    def list_signature_proposals(
        self,
        *,
        status: Optional[str] = "pending",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                """SELECT * FROM signature_proposals
                   WHERE status = ?
                   ORDER BY occurrence_count DESC, proposed_at DESC LIMIT ?""",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM signature_proposals
                   ORDER BY proposed_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def accept_signature_proposal(
        self,
        signature_hash: str,
        accepted_screen_name: str,
    ) -> bool:
        """Mark a proposal accepted. Promotion into screen_signatures is a separate
        operator step — this method only flips the status."""
        conn = self._get_conn()
        cursor = conn.execute(
            """UPDATE signature_proposals
               SET status = 'accepted',
                   accepted_screen_name = ?,
                   accepted_at = ?
               WHERE signature_hash = ? AND status = 'pending'""",
            (accepted_screen_name, datetime.utcnow().isoformat(), signature_hash),
        )
        conn.commit()
        return cursor.rowcount > 0

    def reject_signature_proposal(
        self,
        signature_hash: str,
        reason: str,
    ) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            """UPDATE signature_proposals
               SET status = 'rejected', rejected_reason = ?
               WHERE signature_hash = ? AND status = 'pending'""",
            (reason, signature_hash),
        )
        conn.commit()
        return cursor.rowcount > 0

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

CREATE TABLE IF NOT EXISTS screen_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_screen TEXT NOT NULL,                       -- screen_signatures.screen_name
    intent_verb TEXT NOT NULL,                       -- 'launch' | 'tap' | 'fill_and_continue' | ...
    intent_target TEXT,                              -- element_name for taps, field name for fills
    intent_args_json TEXT,                           -- extra args (text-to-type, key, package)
    to_screen TEXT NOT NULL,                         -- screen_name landed on
    app_context TEXT NOT NULL DEFAULT 'platform',
    confidence REAL DEFAULT 0.5,
    times_used INTEGER DEFAULT 0,
    times_succeeded INTEGER DEFAULT 0,
    last_verified TIMESTAMP,
    source TEXT DEFAULT 'observed',                  -- 'seed' | 'observed' | 'manual'
    UNIQUE(from_screen, intent_verb, intent_target, to_screen, app_context)
);

CREATE INDEX IF NOT EXISTS idx_transitions_from
    ON screen_transitions(from_screen, app_context);

CREATE INDEX IF NOT EXISTS idx_transitions_to
    ON screen_transitions(to_screen, app_context);

CREATE TABLE IF NOT EXISTS game_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,                       -- 'slingo_cash_eruption'
    name TEXT NOT NULL,                              -- 'Slingo Cash Eruption'
    category TEXT,                                   -- 'slingo' | 'slots' | 'live_dealer' | 'arcade'
    provider TEXT,                                   -- 'gaming_realms' | 'igt' | ...
    loaded_signature TEXT,                           -- screen_name of the loaded-game state
    min_bet_usd REAL,
    max_bet_usd REAL,
    play_loop_json TEXT,                             -- per-game play strategy (deferred)
    last_seen TIMESTAMP,
    confidence REAL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS idx_game_catalog_category
    ON game_catalog(category);

CREATE TABLE IF NOT EXISTS observation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_id TEXT,                                     -- workflow run id
    goal_id TEXT,                                    -- which goal was active
    observer_id TEXT NOT NULL,                       -- e.g. obs.jackpot_icon
    severity TEXT NOT NULL DEFAULT 'info',           -- info | warn | bug
    pass_fail TEXT NOT NULL DEFAULT 'n/a',           -- pass | fail | n/a
    matched INTEGER NOT NULL DEFAULT 0,
    auto_handle INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    evidence_path TEXT,
    spec_link TEXT,
    failed_rule TEXT,
    captured_json TEXT,                              -- captured trigger groups
    sub_flow_json TEXT,                              -- queued/run sub_flow tools
    screen_signature TEXT,
    screen_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_observation_log_run
    ON observation_log(run_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_observation_log_observer
    ON observation_log(observer_id, severity);

CREATE TABLE IF NOT EXISTS signature_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signature_hash TEXT NOT NULL UNIQUE,             -- the unk:<hash> from observer
    occurrence_count INTEGER NOT NULL,
    distinct_runs INTEGER NOT NULL,
    candidate_name TEXT,
    top_text_signals_json TEXT,
    top_id_signals_json TEXT,
    last_seen_run_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',          -- pending | accepted | rejected
    accepted_screen_name TEXT,
    accepted_at TIMESTAMP,
    rejected_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_status
    ON signature_proposals(status, proposed_at);

-- ── Spec 005: Casino Game-Play & Verification Suite ──────────────────
-- Per data-model.md §1–§9. All additions are additive and idempotent.
-- The directory/playbook split, stochastic outcomes, frontier, learned
-- waits, round telemetry, logical identity, and clustered proposals
-- are kept as data — never as code branches.

-- §1 Marquee: what's playable. Auto-discovered by lobby-walk.
CREATE TABLE IF NOT EXISTS game_directory (
    slug                    TEXT PRIMARY KEY,
    display_name            TEXT NOT NULL,
    kind                    TEXT NOT NULL,                  -- slingo|slots|blackjack|roulette|...
    aliases_json            TEXT NOT NULL DEFAULT '[]',
    popularity              INTEGER NOT NULL DEFAULT 0,
    available               INTEGER NOT NULL DEFAULT 1,
    loaded_signature        TEXT,
    first_seen_in_lobby_at  TIMESTAMP,
    last_seen_in_lobby_at   TIMESTAMP,
    last_played_at          TIMESTAMP,
    build_env               TEXT NOT NULL DEFAULT 'unknown',
    app_version             TEXT NOT NULL DEFAULT 'unknown',
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_directory_kind        ON game_directory(kind);
CREATE INDEX IF NOT EXISTS ix_directory_popularity  ON game_directory(popularity DESC, last_played_at DESC);

-- §2 House rules: how to play this specific table. Auto-populated on first launch.
CREATE TABLE IF NOT EXISTS game_playbook (
    slug                       TEXT PRIMARY KEY REFERENCES game_directory(slug),
    actions_json               TEXT NOT NULL DEFAULT '{}',
    round_end_signature        TEXT,
    balance_signature          TEXT,
    balance_regex              TEXT,
    bonus_trigger_signatures   TEXT NOT NULL DEFAULT '[]',
    auto_dismiss_signatures    TEXT NOT NULL DEFAULT '[]',
    recovery_json              TEXT NOT NULL DEFAULT '{}',
    rules_json                 TEXT,
    rules_observed_signature   TEXT,
    build_env                  TEXT NOT NULL DEFAULT 'unknown',
    app_version                TEXT NOT NULL DEFAULT 'unknown',
    created_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- §3 Walking the floor: per-screen frontier of (control × tried/untried).
CREATE TABLE IF NOT EXISTS screen_action_frontier (
    screen_sig         TEXT NOT NULL,
    element_id         TEXT NOT NULL,
    attempted_count    INTEGER NOT NULL DEFAULT 0,
    succeeded_count    INTEGER NOT NULL DEFAULT 0,
    last_attempted_at  TIMESTAMP,
    side_effect        TEXT NOT NULL DEFAULT 'idempotent',  -- idempotent|reversible|destructive
    PRIMARY KEY (screen_sig, element_id)
);

-- §4 Doors that lead to multiple rooms: 1-to-N transitions for stochastic outcomes.
CREATE TABLE IF NOT EXISTS transition_outcomes (
    start_sig        TEXT NOT NULL,
    action           TEXT NOT NULL,
    end_sig          TEXT NOT NULL,
    observed_count   INTEGER NOT NULL DEFAULT 1,
    last_seen        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    edge_kind        TEXT NOT NULL DEFAULT 'tap',          -- tap|back|system_back|swipe_*|longpress|type|scroll|deeplink
    side_effect      TEXT NOT NULL DEFAULT 'idempotent',
    precondition     TEXT,                                  -- JSON predicate over RuntimeFacts
    PRIMARY KEY (start_sig, action, end_sig)
);
CREATE INDEX IF NOT EXISTS ix_outcomes_start_action ON transition_outcomes(start_sig, action, observed_count DESC);

-- §5 The night's bets: per-round telemetry.
CREATE TABLE IF NOT EXISTS game_rounds (
    round_id                TEXT PRIMARY KEY,
    workflow_id             TEXT NOT NULL,
    game_slug               TEXT NOT NULL REFERENCES game_directory(slug),
    started_at              TIMESTAMP NOT NULL,
    ended_at                TIMESTAMP,
    bet_amount              REAL,
    balance_before          REAL,
    balance_after           REAL,
    outcome                 TEXT,                            -- win|loss|push|bonus_trigger|error|timeout
    bonus_round_id          TEXT,
    evidence_path           TEXT,
    balance_read_attempts   INTEGER NOT NULL DEFAULT 1,
    notes                   TEXT
);
CREATE INDEX IF NOT EXISTS ix_rounds_workflow ON game_rounds(workflow_id);
CREATE INDEX IF NOT EXISTS ix_rounds_slug     ON game_rounds(game_slug, started_at);

-- §6 Learned waits: how long does a spin take? Per-(game, action, build, version), Welford's online stats.
CREATE TABLE IF NOT EXISTS animation_timings (
    game_slug    TEXT NOT NULL,
    action       TEXT NOT NULL,
    build_env    TEXT NOT NULL,
    app_version  TEXT NOT NULL,
    samples      INTEGER NOT NULL DEFAULT 0,
    mean_ms      INTEGER,
    m2_ms        REAL,                                       -- Welford's running M2 for online stddev
    stddev_ms    INTEGER,
    p95_ms       INTEGER,
    PRIMARY KEY (game_slug, action, build_env, app_version)
);

-- §7 Stable identity across renovations: logical names that survive rehashes.
CREATE TABLE IF NOT EXISTS logical_screens (
    logical_id      TEXT PRIMARY KEY,                        -- e.g. "lobby_home", "slingo_base_grid"
    canonical_name  TEXT NOT NULL,
    description     TEXT,
    is_hub          INTEGER NOT NULL DEFAULT 0,
    staleness_days  INTEGER,                                 -- per-surface decay; null = env default
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logical_elements (
    logical_id        TEXT PRIMARY KEY,                      -- e.g. "spin_button", "search_bar"
    canonical_label   TEXT NOT NULL,
    default_risk_tier TEXT NOT NULL DEFAULT 'low',           -- HIGH for bet/spin/deposit/withdraw/sign-in
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- §8 Provenance: append-only log behind transition_outcomes; 90-day retention.
CREATE TABLE IF NOT EXISTS transition_observations (
    observation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id      TEXT NOT NULL,
    ts               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_sig        TEXT NOT NULL,
    action           TEXT NOT NULL,
    end_sig          TEXT NOT NULL,
    build_env        TEXT NOT NULL,
    app_version      TEXT NOT NULL,
    outcome          TEXT NOT NULL,                          -- success|verify_fail|timeout|error
    duration_ms      INTEGER
);
CREATE INDEX IF NOT EXISTS ix_obs_workflow ON transition_observations(workflow_id);
CREATE INDEX IF NOT EXISTS ix_obs_pair     ON transition_observations(start_sig, action, ts);
"""
