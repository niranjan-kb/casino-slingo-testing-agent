"""run_compare.py — diff two Temporal workflow runs on the metrics that matter.

Used for two purposes:
  1. Spec 005 regression guard — after a code change (planner-prompt overhaul,
     workflow extension, screen-graph migration), re-run the auth smoke and
     diff against a known-good baseline. Hard regressions block merge.
  2. US7 (self-improving loop) — run goal X twice on a stable build with
     operator review of proposals between; the second run should show ≥40%
     fewer LLM calls (SC-004).

Usage:
    uv run scripts/run_compare.py <baseline_run_id> <candidate_run_id> [--workflow-id agent-workflow]

What it diffs:
  - status (COMPLETED / FAILED / TERMINATED)
  - wall-clock duration
  - LLM calls (agent_toolPlanner activity scheduled count)
  - Tool dispatches by type (sum + per-tool deltas)
  - Observer ticks
  - Signal counts
  - Total event count
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple


def fetch_events(workflow_id: str, run_id: str, address: str) -> List[Dict[str, Any]]:
    """Run `temporal workflow show -o json` and return the events array."""
    cmd = [
        "temporal", "workflow", "show",
        "--workflow-id", workflow_id,
        "--run-id", run_id,
        "--address", address,
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"ERR: temporal workflow show failed for run {run_id}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(2)
    payload = json.loads(result.stdout)
    return payload.get("events", []) or []


def metrics_for(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Boil 1000+ workflow events into ~10 numbers we care about for regression diffing."""
    if not events:
        return {"empty": True}

    activity_counts: Dict[str, int] = {}
    signal_counts: Dict[str, int] = {}
    final_event = events[-1]
    failed_activities: List[str] = []

    for ev in events:
        if ev.get("eventType") == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            name = ev.get("activityTaskScheduledEventAttributes", {}).get("activityType", {}).get("name", "?")
            activity_counts[name] = activity_counts.get(name, 0) + 1
        elif ev.get("eventType") == "EVENT_TYPE_ACTIVITY_TASK_FAILED":
            # Track which activities failed (helps spot new failure modes)
            scheduled_id = ev.get("activityTaskFailedEventAttributes", {}).get("scheduledEventId")
            if scheduled_id:
                # Look up the corresponding scheduled event for the activity name
                for sched in events:
                    if (
                        sched.get("eventType") == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED"
                        and sched.get("eventId") == scheduled_id
                    ):
                        nm = sched.get("activityTaskScheduledEventAttributes", {}).get("activityType", {}).get("name", "?")
                        failed_activities.append(nm)
                        break
        elif ev.get("eventType") == "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED":
            sig = ev.get("workflowExecutionSignaledEventAttributes", {}).get("signalName", "?")
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

    start_time = events[0].get("eventTime")
    end_time = final_event.get("eventTime")
    duration_s: float = 0.0
    if start_time and end_time:
        try:
            t0 = datetime.fromisoformat(start_time.rstrip("Z").rstrip())
            t1 = datetime.fromisoformat(end_time.rstrip("Z").rstrip())
            duration_s = (t1 - t0).total_seconds()
        except (TypeError, ValueError):
            pass

    return {
        "status": final_event.get("eventType", "?"),
        "duration_s": duration_s,
        "total_events": len(events),
        "llm_calls": activity_counts.get("agent_toolPlanner", 0),
        "observer_ticks": activity_counts.get("run_observers", 0),
        "tool_dispatches": sum(
            v for k, v in activity_counts.items()
            if k not in {"agent_toolPlanner", "run_observers", "get_wf_env_vars", "mcp_list_tools"}
        ),
        "activity_breakdown": activity_counts,
        "signal_counts": signal_counts,
        "failed_activity_count": len(failed_activities),
        "failed_activities": failed_activities[:5],  # sample
    }


def diff(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Return (regressions, improvements) — human-readable lines."""
    regressions: List[str] = []
    improvements: List[str] = []
    if baseline.get("empty") or candidate.get("empty"):
        return ["one or both runs have no events"], []

    # Status comparison — hard requirement
    if candidate["status"] != baseline["status"]:
        regressions.append(
            f"status changed: {baseline['status']} → {candidate['status']}"
        )

    # LLM call delta — main cost / regression signal
    base_llm = baseline["llm_calls"]
    cand_llm = candidate["llm_calls"]
    if base_llm > 0:
        pct = (cand_llm - base_llm) / base_llm * 100.0
        line = f"llm_calls: {base_llm} → {cand_llm} ({pct:+.1f}%)"
        if pct > 10:
            regressions.append(line + "  ⚠️ +10% threshold")
        elif pct < -10:
            improvements.append(line + "  ✓ improvement")
        else:
            improvements.append(line + "  (within ±10%)")

    # Duration delta
    bd, cd = baseline["duration_s"], candidate["duration_s"]
    if bd > 0:
        pct = (cd - bd) / bd * 100.0
        line = f"duration: {bd:.0f}s → {cd:.0f}s ({pct:+.1f}%)"
        if pct > 25:
            regressions.append(line + "  ⚠️ +25% threshold")
        else:
            improvements.append(line)

    # Activity-by-type deltas
    base_acts = baseline["activity_breakdown"]
    cand_acts = candidate["activity_breakdown"]
    all_acts = sorted(set(base_acts) | set(cand_acts))
    activity_lines: List[str] = []
    for act in all_acts:
        b = base_acts.get(act, 0)
        c = cand_acts.get(act, 0)
        if b == c:
            continue
        delta = c - b
        sign = "+" if delta > 0 else ""
        activity_lines.append(f"  {act}: {b} → {c} ({sign}{delta})")
    if activity_lines:
        improvements.append("activity deltas:\n" + "\n".join(activity_lines))

    # Failed activities
    if candidate["failed_activity_count"] > baseline["failed_activity_count"]:
        regressions.append(
            f"failed_activity_count: {baseline['failed_activity_count']} → "
            f"{candidate['failed_activity_count']}; sample: {candidate['failed_activities']}"
        )

    return regressions, improvements


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_run_id")
    parser.add_argument("candidate_run_id")
    parser.add_argument("--workflow-id", default="agent-workflow")
    parser.add_argument("--address", default="localhost:7233")
    args = parser.parse_args()

    print(f"# Run comparison\n")
    print(f"baseline:   {args.baseline_run_id}")
    print(f"candidate:  {args.candidate_run_id}\n")

    base_events = fetch_events(args.workflow_id, args.baseline_run_id, args.address)
    cand_events = fetch_events(args.workflow_id, args.candidate_run_id, args.address)

    base = metrics_for(base_events)
    cand = metrics_for(cand_events)

    print("## Baseline")
    print(json.dumps({k: v for k, v in base.items() if k != "activity_breakdown"}, indent=2))
    print("\n## Candidate")
    print(json.dumps({k: v for k, v in cand.items() if k != "activity_breakdown"}, indent=2))

    regressions, improvements = diff(base, cand)
    print("\n## Diff\n")
    if regressions:
        print("### REGRESSIONS")
        for line in regressions:
            print(f"- {line}")
    else:
        print("### REGRESSIONS\n(none)\n")
    if improvements:
        print("\n### Improvements / unchanged")
        for line in improvements:
            print(f"- {line}")

    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
