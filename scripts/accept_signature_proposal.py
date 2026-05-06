"""Operator-only: accept or reject a pending signature proposal (MW-4 / FR-022).

This is the explicit step that promotes a recurring unknown screen into the
agent's named-screen catalog. Auto-promotion is forbidden by spec — every
acceptance must be a deliberate operator action.

Usage:
    uv run scripts/accept_signature_proposal.py <unk:hash> --as <screen_name> [--seed-signatures]
    uv run scripts/accept_signature_proposal.py <unk:hash> --reject "reason"
"""
from __future__ import annotations

import argparse
import json
import sys

from shared.screen_map_db import ScreenMapDB


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("signature_hash", help="the unk:<hash> id to act on")
    parser.add_argument("--as", dest="screen_name",
                        help="screen_name to promote the proposal to (with --as)")
    parser.add_argument("--reject", dest="reason",
                        help="reject the proposal with this reason")
    parser.add_argument("--seed-signatures", action="store_true",
                        help="after accepting, seed top text/id signals into screen_signatures")
    args = parser.parse_args()

    if not args.signature_hash.startswith("unk:"):
        print(f"ERROR: signature_hash must start with 'unk:' (got {args.signature_hash})", file=sys.stderr)
        return 2
    if not (args.screen_name or args.reason):
        print("ERROR: pass either --as <screen_name> OR --reject <reason>.", file=sys.stderr)
        return 2

    db = ScreenMapDB()

    if args.reason:
        ok = db.reject_signature_proposal(args.signature_hash, args.reason)
        if not ok:
            print(f"WARN: no pending proposal with hash {args.signature_hash}")
            return 1
        print(f"Rejected {args.signature_hash}: {args.reason}")
        return 0

    ok = db.accept_signature_proposal(args.signature_hash, args.screen_name)
    if not ok:
        print(f"WARN: no pending proposal with hash {args.signature_hash}")
        return 1
    print(f"Accepted {args.signature_hash} as '{args.screen_name}'.")

    if args.seed_signatures:
        # Pull the top signals from the proposal row and seed them.
        conn = db._get_conn()
        row = conn.execute(
            "SELECT top_text_signals_json, top_id_signals_json FROM signature_proposals "
            "WHERE signature_hash = ?",
            (args.signature_hash,),
        ).fetchone()
        if row:
            seeded = 0
            for sig_type, blob in (("element_text", row["top_text_signals_json"]),
                                    ("element_id", row["top_id_signals_json"])):
                if not blob:
                    continue
                try:
                    values = json.loads(blob)
                except (TypeError, ValueError):
                    continue
                for value in values:
                    db.upsert_screen_signature(
                        screen_name=args.screen_name,
                        app_context="platform",
                        signature_type=sig_type,
                        signature_value=str(value),
                        priority=1,
                    )
                    seeded += 1
            print(f"Seeded {seeded} signature(s) into screen_signatures for '{args.screen_name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
