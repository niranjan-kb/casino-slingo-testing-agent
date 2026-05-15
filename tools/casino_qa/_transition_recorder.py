"""Spec 005 T044: write to `transition_outcomes` + `transition_observations`.

Sits beside the legacy `record_transition_observation` (which writes to the
old `screen_transitions` table) so we keep the existing path planner
working while populating the new stochastic-outcomes tables.

All writes are best-effort (FR-027): a DB failure here logs a warning
and returns; the caller keeps running.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from temporalio import activity

log = logging.getLogger(__name__)


def _build_meta() -> tuple[str, str]:
    return os.getenv("BUILD_ENV", "unknown"), os.getenv("APP_VERSION", "unknown")


def _workflow_id() -> str:
    """Read the current workflow id from the activity context.

    Outside an activity (e.g. unit tests calling the tool directly) this
    raises; we swallow and return an empty string so the recorder still
    UPSERTs the outcome row even without an activity context.
    """
    try:
        return activity.info().workflow_id
    except Exception:                                       # noqa: BLE001
        return ""


def record_outcome_safely(
    db: Any,
    *,
    start_sig: str,
    action: str,
    end_sig: str,
    edge_kind: str = "tap",
    side_effect: str = "idempotent",
    outcome: str = "success",
    duration_ms: Optional[int] = None,
) -> None:
    """UPSERT transition_outcomes + append transition_observations row.

    Both writes are independent: an outcomes-table failure does not skip
    the event-log write, and vice versa. FR-027 is honoured throughout.
    """
    if db is None or not start_sig or not end_sig or start_sig == end_sig:
        return  # nothing to learn from a no-op transition
    build_env, app_version = _build_meta()
    workflow_id = _workflow_id()
    try:
        db.upsert_transition_outcome(
            start_sig, action, end_sig,
            edge_kind=edge_kind, side_effect=side_effect,
        )
    except Exception as e:                                  # noqa: BLE001 — FR-027
        log.warning(
            "upsert_transition_outcome failed (start=%s action=%s end=%s): %s",
            start_sig, action, end_sig, e,
        )
    try:
        db.record_transition_observation_event(
            workflow_id=workflow_id,
            start_sig=start_sig, action=action, end_sig=end_sig,
            build_env=build_env, app_version=app_version,
            outcome=outcome, duration_ms=duration_ms,
        )
    except Exception as e:                                  # noqa: BLE001 — FR-027
        log.warning(
            "record_transition_observation_event failed (start=%s action=%s end=%s): %s",
            start_sig, action, end_sig, e,
        )
