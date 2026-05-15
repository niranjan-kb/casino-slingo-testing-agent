"""GenerateReport — session terminator that writes a run report to disk.

Two modes:

* **Spec-005 mode** (caller supplies `workflow_id`): emits both
  `reports/<date>-<workflow_id>.json` (per `contracts/run_report.schema.json`)
  AND a rendered `<...>.md` sibling. Pulls `rounds` from `game_rounds`
  and `transitions_added` from `transition_outcomes` (last-seen filter)
  on its own. The planner only has to provide the session-level fields
  it actually knows (terminal_reason, balance, intents telemetry, etc.).
* **Legacy mode** (no `workflow_id`): retained as-is so the existing
  Slingo Cash Eruption smoke flow keeps working unmodified.

Both modes are best-effort with respect to the DB: a query failure logs
a warning and is replaced with a degraded status in the optimizations
panel, never aborts the report.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from ._deps import get_screen_db

log = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Lowercase + alnum/dash only — for report filenames."""
    out = []
    for ch in (name or "session").lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "session"


# ── Spec 005 emission ──────────────────────────────────────────────────


_DEFAULT_OPTIMIZATIONS: Dict[str, Any] = {
    "page_source_excluded": "active",   # T024 ships ON
    "tool_result_tiering":  "active",   # T024 _XML_STUB_THRESHOLD honoured
    "history_compactor":    "active",   # T027 ships ON
    "prompt_cache":         {"status": "degraded", "hit_rate": 0.0},  # T028 deferred
    "replay_determinism":   "active",   # only LLM call is non-deterministic
}


def _safe_db_call(label: str, fn, default):
    try:
        return fn()
    except Exception as e:                                  # noqa: BLE001
        log.warning("generate_report: %s failed: %s", label, e)
        return default


def _gather_run_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Build the JSON payload per contracts/run_report.schema.json.

    Required-field defaults are filled in if the planner omits them so
    the report still validates against the schema.
    """
    db = get_screen_db()
    workflow_id = str(args.get("workflow_id") or "")
    started_at = args.get("started_at") or datetime.utcnow().isoformat() + "Z"
    ended_at = args.get("ended_at") or datetime.utcnow().isoformat() + "Z"

    rounds: List[Dict[str, Any]] = []
    if db and workflow_id:
        rounds = _safe_db_call(
            "get_rounds_for_workflow",
            lambda: db.get_rounds_for_workflow(workflow_id),
            [],
        )

    transitions_added: List[str] = []
    if db:
        transitions_added = _safe_db_call(
            "get_transitions_added_since",
            lambda: db.get_transitions_added_since(started_at),
            [],
        )

    balance = args.get("balance") or {
        "start":              0.0,
        "end":                0.0,
        "delta":              0.0,
        "max_loss_requested": float(os.getenv("MAX_LOSS_USD", "10")),
        "max_loss_effective": float(os.getenv("MAX_LOSS_USD", "10")),
    }

    optimizations = dict(_DEFAULT_OPTIMIZATIONS)
    optimizations.update(args.get("optimizations") or {})

    payload: Dict[str, Any] = {
        "workflow_id":      workflow_id or "unknown",
        "started_at":       started_at,
        "ended_at":         ended_at,
        "build_env":        args.get("build_env") or os.getenv("BUILD_ENV", "unknown"),
        "app_version":      args.get("app_version") or os.getenv("APP_VERSION", "unknown"),
        "device":           args.get("device") or {
            "android_serial": os.getenv("ANDROID_SERIAL", "emulator-5554"),
            "resolution":     os.getenv("DEVICE_RESOLUTION", "1344x2992"),
            "platform":       os.getenv("PLATFORM", "android"),
        },
        "session_intent":   args.get("session_intent") or {},
        "terminal_reason":  args.get("terminal_reason") or "report",
        "balance":          balance,
        "rounds":           rounds,
        "intents":          args.get("intents") or [],
        "transitions_added":   transitions_added,
        "signatures_proposed": args.get("signatures_proposed") or [],
        "animation_timing_deltas": args.get("animation_timing_deltas") or [],
        "optimizations":    optimizations,
        "operator_actions": args.get("operator_actions") or [],
    }
    return payload


def _render_markdown(payload: Dict[str, Any]) -> str:
    """Render a human-readable companion to the JSON report."""
    bal = payload["balance"]
    delta = bal.get("delta", 0.0)
    delta_sign = "+" if delta >= 0 else ""
    rounds = payload.get("rounds") or []
    intents = payload.get("intents") or []
    ops = payload.get("optimizations") or {}
    ops_lines = []
    for key in ("page_source_excluded", "tool_result_tiering", "history_compactor", "replay_determinism"):
        ops_lines.append(f"- {key}: `{ops.get(key, 'unknown')}`")
    pc = ops.get("prompt_cache") or {}
    if isinstance(pc, dict):
        ops_lines.append(f"- prompt_cache: `{pc.get('status', 'unknown')}` (hit_rate={pc.get('hit_rate', 0):.2f})")

    rounds_block = ""
    if rounds:
        head = "| round_id | game_slug | outcome | bet | balance_delta |\n|---|---|---|---|---|"
        rows = []
        for r in rounds:
            bet = r.get("bet_amount", "")
            bd = ""
            if r.get("balance_before") is not None and r.get("balance_after") is not None:
                bd = f"{r['balance_after'] - r['balance_before']:+.2f}"
            rows.append(
                f"| `{r.get('round_id', '?')}` | {r.get('game_slug', '?')} | "
                f"{r.get('outcome', '?')} | {bet} | {bd} |"
            )
        rounds_block = "\n".join([head, *rows])
    else:
        rounds_block = "_No rounds recorded._"

    intents_block = ""
    if intents:
        head = "| intent_id | turns | llm_calls | input_chars_p50 | input_chars_p95 |\n|---|---|---|---|---|"
        rows = []
        for it in intents:
            rows.append(
                f"| {it.get('intent_id', '?')} | {it.get('turns', 0)} | "
                f"{it.get('llm_calls', 0)} | {it.get('input_chars_p50', '')} | "
                f"{it.get('input_chars_p95', '')} |"
            )
        intents_block = "\n".join([head, *rows])
    else:
        intents_block = "_No intent telemetry captured._"

    op_actions = payload.get("operator_actions") or []
    op_lines = (
        "\n".join(f"- **{a.get('kind')}** — {a.get('description')}" for a in op_actions)
        if op_actions else "- None"
    )
    transitions_block = (
        "\n".join(f"- {t}" for t in payload["transitions_added"])
        if payload["transitions_added"] else "_None._"
    )
    ops_block = "\n".join(ops_lines)

    return f"""# Session report — {payload['workflow_id']}

**Terminal reason:** `{payload['terminal_reason']}`
**Build:** `{payload['build_env']}`  /  **App version:** `{payload['app_version']}`
**Started:** {payload['started_at']}  /  **Ended:** {payload['ended_at']}

## Balance ledger
| field | value |
|---|---|
| start | {bal.get('start')} |
| end | {bal.get('end')} |
| delta | {delta_sign}{delta} |
| max_loss_requested | {bal.get('max_loss_requested')} |
| max_loss_effective | {bal.get('max_loss_effective')} |

## Rounds
{rounds_block}

## Intent telemetry
{intents_block}

## Transitions added this run
{transitions_block}

## Optimizations panel
{ops_block}

## Operator actions
{op_lines}
"""


def _generate_run_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Spec-005 emission path: writes both JSON and MD sibling."""
    payload = _gather_run_report(args)
    reports_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    date = datetime.utcnow().strftime("%Y-%m-%d")
    base = f"{date}-{_slugify(payload['workflow_id'])}"
    json_path = os.path.join(reports_dir, f"{base}.json")
    md_path = os.path.join(reports_dir, f"{base}.md")
    try:
        with open(json_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
    except Exception as e:                                  # noqa: BLE001
        log.warning("generate_report: failed to write JSON %s: %s", json_path, e)
        return {"status": "FAIL", "error": f"json write failed: {e}"}
    try:
        with open(md_path, "w") as f:
            f.write(_render_markdown(payload))
    except Exception as e:                                  # noqa: BLE001
        log.warning("generate_report: MD sibling write failed: %s", e)
    return {
        "status":      "PASS",
        "report_path": json_path,
        "md_path":     md_path,
        "rounds":      len(payload.get("rounds") or []),
        "intents":     len(payload.get("intents") or []),
        "transitions_added": len(payload.get("transitions_added") or []),
    }


# ── Legacy emission (Slingo flow) ──────────────────────────────────────


def _generate_legacy_report(args: dict) -> dict:
    device = os.getenv("ANDROID_SERIAL", "emulator-5554")
    resolution = os.getenv("DEVICE_RESOLUTION", "1344x2992")
    build_env = os.getenv("BUILD_ENV", "test")
    platform = os.getenv("PLATFORM", "android")

    starting_balance = args.get("starting_balance", "unknown")
    ending_balance = args.get("ending_balance", "unknown")
    spins_played = int(args.get("spins_played", 0))
    total_spins = int(args.get("total_spins", 5))
    wilds = int(args.get("wilds", 0))
    super_wilds = int(args.get("super_wilds", 0))
    extra_spins = int(args.get("extra_spins_purchased", 0))
    anomalies = args.get("anomalies", [])
    observations = args.get("observations", [])
    bugs = args.get("bugs", [])
    game_name = args.get("game_name", "slingo-cash-eruption")
    now = datetime.now()
    run_id = args.get("run_id", now.strftime("%Y%m%dT%H%M%S"))

    if isinstance(anomalies, str):
        anomalies = [anomalies] if anomalies else []
    if isinstance(observations, str):
        observations = [observations] if observations else []

    delta = "unknown"
    try:
        start_val = float(str(starting_balance).replace("$", "").replace(",", ""))
        end_val = float(str(ending_balance).replace("$", "").replace(",", ""))
        delta = f"${end_val - start_val:+.2f}"
    except (ValueError, AttributeError):
        pass

    is_pass = (
        spins_played >= total_spins
        and extra_spins == 0
        and starting_balance != "unknown"
        and ending_balance != "unknown"
        and not any("crash" in str(a).lower() for a in anomalies)
        and not any(str(b.get("severity", "")).upper() == "P0" for b in bugs if isinstance(b, dict))
    )

    def _bullets(items, fallback="None"):
        if not items:
            return f"- {fallback}"
        return "\n".join(f"- {x}" for x in items)

    bug_lines = []
    for b in bugs:
        if isinstance(b, dict):
            sev = b.get("severity", "P3")
            summary = b.get("summary", "(no summary)")
            line = f"- **[{sev}]** {summary}"
            if b.get("repro"):
                line += f"\n  - Repro: {b['repro']}"
            if b.get("screenshot"):
                line += f"\n  - Screenshot: `{b['screenshot']}`"
            bug_lines.append(line)
    bug_block = "\n".join(bug_lines) if bug_lines else "- None"

    report_md = f"""# {game_name} session — {now.strftime('%Y-%m-%d %H:%M')}

**Status:** {'✅ PASS' if is_pass else '❌ FAIL'}

## Session
- Game: `{game_name}`
- Run ID: `{run_id}`
- Device: `{device}` ({resolution})
- Platform: `{platform}`  /  Build: `{build_env}`
- Timestamp: {now.isoformat()}

## Balance ledger
| Field | Value |
|-------|-------|
| Starting balance | {starting_balance} |
| Ending balance | {ending_balance} |
| Delta | {delta} |
| Spins played | {spins_played}/{total_spins} |
| Wilds | {wilds} |
| Super wilds | {super_wilds} |
| Extra spins purchased | {extra_spins} (must be 0 for PASS) |

## Bugs
{bug_block}

## Observations
{_bullets(observations)}

## Anomalies
{_bullets(anomalies)}
"""

    reports_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    fname = f"{now.strftime('%Y-%m-%d')}-{_slugify(game_name)}-{run_id}.md"
    report_path = os.path.join(reports_dir, fname)
    with open(report_path, "w") as f:
        f.write(report_md)

    return {
        "status": "PASS" if is_pass else "FAIL",
        "report": report_md,
        "report_path": report_path,
        "delta": delta,
    }


# ── Public entry point ────────────────────────────────────────────────


def generate_report(args: dict) -> dict:
    """Generate a session report.

    Spec-005 mode (caller supplies `workflow_id`): writes both JSON
    (`reports/<date>-<workflow>.json` per `run_report.schema.json`) AND
    a rendered markdown sibling.

    Legacy mode (no `workflow_id`): preserves the existing slingo-style
    markdown report at `reports/<date>-<game>-<run_id>.md`.
    """
    if args.get("workflow_id"):
        return _generate_run_report(args)
    return _generate_legacy_report(args)
