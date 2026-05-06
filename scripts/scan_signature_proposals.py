"""Sweep observation_log for recurring unknown-screen signatures (MW-4 / FR-021).

When the unknown_screen observer fires for the same `unk:<hash>` signature
≥ 3 times across ≥ 2 distinct runs, this script upserts a row into
`signature_proposals` (status='pending') for human/LLM-with-context review.
Auto-promotion is forbidden (FR-022) — accept via:

    uv run scripts/accept_signature_proposal.py <unk:hash> --as <screen_name>

Usage:
    uv run scripts/scan_signature_proposals.py [--min-occurrences 3] [--min-runs 2]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any, Dict, List

from shared.screen_map_db import ScreenMapDB


def _extract_signals(captured_json_blob: str) -> Dict[str, List[str]]:
    """Pull the top text + id signals out of an observation_log row's captured_json.

    The unknown_screen observer stores the matched groups under `groups`; older
    rows may use different shapes. Be tolerant.
    """
    if not captured_json_blob:
        return {"text": [], "ids": []}
    try:
        blob = json.loads(captured_json_blob)
    except (TypeError, ValueError):
        return {"text": [], "ids": []}
    text_signals = blob.get("top_text") or blob.get("texts") or []
    id_signals = blob.get("top_ids") or blob.get("resource_ids") or []
    return {
        "text": [str(s) for s in text_signals[:5]],
        "ids": [str(s) for s in id_signals[:5]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--print-only", action="store_true",
                        help="report what WOULD be upserted; do not write")
    args = parser.parse_args()

    db = ScreenMapDB()
    conn = db._get_conn()

    rows = conn.execute(
        """SELECT screen_signature, run_id, captured_json, summary, timestamp
           FROM observation_log
           WHERE observer_id = 'obs.unknown_screen'
             AND screen_signature LIKE 'unk:%'
           ORDER BY timestamp ASC"""
    ).fetchall()

    bucket: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "runs": set(), "captured": None, "last_run": None}
    )
    for row in rows:
        sig = row["screen_signature"]
        bucket[sig]["count"] += 1
        if row["run_id"]:
            bucket[sig]["runs"].add(row["run_id"])
            bucket[sig]["last_run"] = row["run_id"]
        if not bucket[sig]["captured"]:
            bucket[sig]["captured"] = row["captured_json"]

    eligible: List[Dict[str, Any]] = []
    for sig, info in bucket.items():
        if info["count"] >= args.min_occurrences and len(info["runs"]) >= args.min_runs:
            signals = _extract_signals(info["captured"] or "")
            eligible.append({
                "signature_hash": sig,
                "occurrence_count": info["count"],
                "distinct_runs": len(info["runs"]),
                "last_seen_run_id": info["last_run"],
                "top_text": signals["text"],
                "top_ids": signals["ids"],
            })

    if not eligible:
        print(f"No proposals — no unknown signatures meet "
              f"≥{args.min_occurrences} hits across ≥{args.min_runs} runs.")
        return 0

    print(f"{len(eligible)} signature(s) eligible:")
    for prop in sorted(eligible, key=lambda p: -p["occurrence_count"]):
        print(f"\n  {prop['signature_hash']}")
        print(f"    occurrences: {prop['occurrence_count']} across {prop['distinct_runs']} runs")
        if prop["top_text"]:
            print(f"    top_text:    {prop['top_text']}")
        if prop["top_ids"]:
            print(f"    top_ids:     {prop['top_ids']}")
        if not args.print_only:
            db.upsert_signature_proposal(
                signature_hash=prop["signature_hash"],
                occurrence_count=prop["occurrence_count"],
                distinct_runs=prop["distinct_runs"],
                top_text_signals=prop["top_text"],
                top_id_signals=prop["top_ids"],
                last_seen_run_id=prop["last_seen_run_id"],
            )
    if args.print_only:
        print("\n(--print-only set — no proposals written)")
    else:
        print(f"\nUpserted {len(eligible)} proposal(s) into signature_proposals.")
        print("Review with: SELECT * FROM signature_proposals WHERE status='pending';")
        print("Accept via:  uv run scripts/accept_signature_proposal.py <unk:hash> --as <screen_name>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
