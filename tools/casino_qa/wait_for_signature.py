"""WaitForSignature — learned wait for a target screen signature.

Per spec 005 T040 / research §R8 / FR-021. Replaces hardcoded
`WaitSeconds(N)` for game-action waits. Three-stage timeout:

    1. learned: when ≥5 samples in animation_timings for
       (game_slug, action, build_env, app_version), use p95 + 2σ
    2. kind default: kind file's `learned_default` ms
    3. stable-UI fallback: poll for DOM stability (no change for 800ms)

This tool is a *planner* — it computes the timeout and writes the sample
contributions back. The actual polling/screen-detection happens via
DetectScreen + WaitSeconds in the goal loop. Why the split? Replay
determinism: this activity returns deterministic numbers from the DB; the
detection is the non-deterministic part and lives behind its existing
activity boundaries.

Anti-hardcoding: nothing per-game in this file. Animation magnitudes come
from the DB (samples) or from `game_kinds/<kind>.md::Animation defaults`,
which is data not code.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional

from ._deps import get_screen_db


# Stable-UI fallback constants. Overridable via env so test suites can run
# with shorter polling cadences without touching code.
_STABLE_UI_DEFAULT_MS = int(os.getenv("WAIT_STABLE_UI_MS", "800"))
_KIND_FALLBACK_MS = int(os.getenv("WAIT_KIND_FALLBACK_MS", "5000"))
_MIN_SAMPLES_FOR_LEARNED = int(os.getenv("WAIT_MIN_SAMPLES_FOR_LEARNED", "5"))
_HARD_CAP_MS = int(os.getenv("WAIT_FOR_SIGNATURE_HARD_CAP_MS", "30000"))


def wait_for_signature(args: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the timeout for a learned wait + record a sample.

    Args:
        game_slug:        str   — game_directory.slug (per-game keying)
        action:           str   — "spin" | "bonus_intro" | "deal_card" | ...
        build_env:        str   — runtime build_env (cert/test/prod-debug)
        app_version:      str   — app version string
        kind_default_ms:  int?  — fallback from game_kinds/<kind>.md
        observed_ms:      int?  — when present, contribute a sample (Welford)

    Returns:
        {
            "timeout_ms":      int,
            "samples":         int,
            "stable_ui_ms":    int,             # fallback poll cadence
            "source":          "learned"|"kind_default"|"stable_ui_only",
            "stats":           {mean_ms, stddev_ms, p95_ms} | null,
            "sample_recorded": bool,
        }
    """
    game_slug = (args.get("game_slug") or "").strip()
    action = (args.get("action") or "").strip()
    build_env = (args.get("build_env") or "unknown").strip()
    app_version = (args.get("app_version") or "unknown").strip()
    kind_default_ms = _safe_int(args.get("kind_default_ms")) or _KIND_FALLBACK_MS
    observed_ms = _safe_int(args.get("observed_ms"))

    if not game_slug or not action:
        return _no_db_response(kind_default_ms, source="kind_default")

    db = get_screen_db()
    if db is None:
        return _no_db_response(kind_default_ms, source="kind_default")

    # Read existing stats. Online-update when we have a sample to contribute.
    stats = _load_timing_row(db, game_slug, action, build_env, app_version)
    sample_recorded = False
    if observed_ms is not None and observed_ms > 0:
        stats = _update_welford(
            db, game_slug, action, build_env, app_version, observed_ms, stats
        )
        sample_recorded = True

    samples = stats["samples"] if stats else 0

    # Pick timeout source by sample count.
    if stats and samples >= _MIN_SAMPLES_FOR_LEARNED and stats.get("p95_ms"):
        learned = int(stats["p95_ms"]) + 2 * int(stats.get("stddev_ms") or 0)
        timeout_ms = min(_HARD_CAP_MS, max(stats["p95_ms"], learned))
        source = "learned"
    elif kind_default_ms:
        timeout_ms = min(_HARD_CAP_MS, kind_default_ms)
        source = "kind_default"
    else:
        timeout_ms = _STABLE_UI_DEFAULT_MS
        source = "stable_ui_only"

    return {
        "timeout_ms": timeout_ms,
        "samples": samples,
        "stable_ui_ms": _STABLE_UI_DEFAULT_MS,
        "source": source,
        "stats": _trim_stats(stats),
        "sample_recorded": sample_recorded,
    }


# ── DB IO + Welford ──────────────────────────────────────────────────────


def _load_timing_row(
    db: Any, slug: str, action: str, build_env: str, app_version: str
) -> Optional[Dict[str, Any]]:
    try:
        row = db._get_conn().execute(
            "SELECT samples, mean_ms, m2_ms, stddev_ms, p95_ms FROM animation_timings "
            "WHERE game_slug = ? AND action = ? AND build_env = ? AND app_version = ?",
            (slug, action, build_env, app_version),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "samples": int(row["samples"] or 0),
        "mean_ms": int(row["mean_ms"] or 0),
        "m2_ms": float(row["m2_ms"] or 0.0),
        "stddev_ms": int(row["stddev_ms"] or 0),
        "p95_ms": int(row["p95_ms"] or 0),
    }


def _update_welford(
    db: Any,
    slug: str,
    action: str,
    build_env: str,
    app_version: str,
    observed_ms: int,
    prior: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Online mean / stddev via Welford. Persist to animation_timings.

    p95 is approximated as `mean + 1.645 * stddev` (normal-approx; cheap and
    good-enough for animation timings which are tightly clustered around a
    handful of frames). Replaced by a real percentile estimator if/when we
    accumulate enough samples to need one.
    """
    if prior is None:
        prior = {"samples": 0, "mean_ms": 0, "m2_ms": 0.0, "stddev_ms": 0, "p95_ms": 0}
    n = prior["samples"] + 1
    mean = prior["mean_ms"]
    m2 = prior["m2_ms"]
    delta = observed_ms - mean
    new_mean = mean + delta / n
    delta2 = observed_ms - new_mean
    new_m2 = m2 + delta * delta2
    new_var = (new_m2 / (n - 1)) if n > 1 else 0.0
    new_stddev = int(math.sqrt(new_var)) if new_var > 0 else 0
    new_p95 = int(new_mean + 1.645 * new_stddev)

    updated = {
        "samples": n,
        "mean_ms": int(new_mean),
        "m2_ms": float(new_m2),
        "stddev_ms": new_stddev,
        "p95_ms": new_p95,
    }

    try:
        db._get_conn().execute(
            "INSERT INTO animation_timings(game_slug, action, build_env, app_version, "
            "    samples, mean_ms, m2_ms, stddev_ms, p95_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(game_slug, action, build_env, app_version) DO UPDATE SET "
            "    samples = excluded.samples, mean_ms = excluded.mean_ms, "
            "    m2_ms = excluded.m2_ms, stddev_ms = excluded.stddev_ms, "
            "    p95_ms = excluded.p95_ms",
            (
                slug, action, build_env, app_version,
                updated["samples"], updated["mean_ms"], updated["m2_ms"],
                updated["stddev_ms"], updated["p95_ms"],
            ),
        )
        db._get_conn().commit()
    except Exception:
        pass  # observers never halt the run

    return updated


# ── small helpers ──


def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _trim_stats(stats: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if stats is None:
        return None
    return {k: stats[k] for k in ("samples", "mean_ms", "stddev_ms", "p95_ms") if k in stats}


def _no_db_response(kind_default_ms: int, *, source: str) -> Dict[str, Any]:
    return {
        "timeout_ms": min(_HARD_CAP_MS, kind_default_ms or _STABLE_UI_DEFAULT_MS),
        "samples": 0,
        "stable_ui_ms": _STABLE_UI_DEFAULT_MS,
        "source": source,
        "stats": None,
        "sample_recorded": False,
    }
