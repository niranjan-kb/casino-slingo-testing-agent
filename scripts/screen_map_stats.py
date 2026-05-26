"""
Show screen map DB stats — confidence scores, verification history, improvements.

Run: uv run scripts/screen_map_stats.py [--device DEVICE_ID] [--low-confidence]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.screen_map_db import ScreenMapDB


def confidence_bar(conf: float, width: int = 20) -> str:
    """Visual confidence bar."""
    filled = int(conf * width)
    return f"[{'#' * filled}{'.' * (width - filled)}] {conf:.0%}"


def print_device_report(db: ScreenMapDB, profile_id: str):
    conn = db._get_conn()

    # Header
    print(f"\n{'=' * 70}")
    print(f"  Device: {profile_id}")
    print(f"{'=' * 70}")

    # Elements by screen, grouped by app_context
    rows = conn.execute(
        """SELECT app_context, screen_name, element_name, x, y,
                  confidence, times_used, times_succeeded, source, last_verified
           FROM screen_elements
           WHERE device_profile_id = ?
           ORDER BY app_context, screen_name, element_name""",
        (profile_id,),
    ).fetchall()

    if not rows:
        print("  No elements stored for this device.\n")
        return

    current_context = None
    current_screen = None
    total = 0
    graduated = 0  # confidence >= 0.9
    needs_work = 0  # confidence < 0.5
    never_tested = 0  # times_used == 0

    for r in rows:
        total += 1
        ctx = r["app_context"]
        screen = r["screen_name"]

        if ctx != current_context:
            current_context = ctx
            print(f"\n  --- {ctx.upper()} ---")

        if screen != current_screen:
            current_screen = screen
            print(f"\n  [{screen}]")

        conf = r["confidence"] or 0
        used = r["times_used"] or 0
        succeeded = r["times_succeeded"] or 0
        source = r["source"] or "?"

        if conf >= 0.9 and used >= 3:
            graduated += 1
            status = "GRAD"
        elif used == 0:
            never_tested += 1
            status = "NEW "
        elif conf < 0.5:
            needs_work += 1
            status = "LOW "
        else:
            status = "    "

        bar = confidence_bar(conf)
        usage = f"{succeeded}/{used}" if used > 0 else "untested"
        print(f"    {status} {r['element_name']:25s} ({r['x']:4d},{r['y']:4d}) {bar} {usage:>7s}  src={source}")

    # Summary
    print(f"\n  {'─' * 50}")
    print(f"  Total elements:    {total}")
    print(f"  Graduated (>=90%): {graduated}  {'  << ready to skip verification' if graduated > 0 else ''}")
    print(f"  Needs work (<50%): {needs_work}")
    print(f"  Never tested:      {never_tested}")
    print()


def print_recent_corrections(db: ScreenMapDB, profile_id: str = None, limit: int = 10):
    print(f"\n{'=' * 70}")
    print(f"  Recent Corrections (learning events)")
    print(f"{'=' * 70}")

    # Spec 006 T604: `run_observations` was dropped. The corrections data
    # used to live there; until/unless we rewire from observation_log,
    # this stats block stays empty.
    obs: list = []
    corrections = [o for o in obs if o.get("correction")]

    if not corrections:
        print("  No corrections recorded yet.\n")
        return

    for o in corrections:
        ts = (o.get("timestamp") or "")[:19]
        print(f"  [{ts}] {o['action']} {o['element_name']} on {o['screen_name']}")
        print(f"           expected: {o['expected_result']}")
        print(f"           actual:   {o['actual_result']}")
        print(f"           fix:      {o['correction']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Screen map DB stats")
    parser.add_argument("--device", default=None, help="Filter to specific device profile ID")
    parser.add_argument("--low-confidence", action="store_true", help="Show only low-confidence elements")
    parser.add_argument("--db-path", default=None, help="Override DB path")
    args = parser.parse_args()

    db = ScreenMapDB(args.db_path) if args.db_path else ScreenMapDB()
    profiles = db.list_device_profiles()

    print(f"\nDB: {db.db_path}")
    stats = db.get_stats()
    print(f"   {stats['devices']} devices, {stats['elements']} elements, "
          f"{stats['signatures']} signatures, {stats['observations']} observations")

    if args.low_confidence:
        print(f"\n  Low-confidence elements (< 0.5):")
        for p in profiles:
            low = db.get_low_confidence_elements(p["id"], threshold=0.5)
            if low:
                print(f"\n  [{p['id']}]")
                for e in low:
                    bar = confidence_bar(e["confidence"] or 0)
                    print(f"    {e['screen_name']}.{e['element_name']:20s} ({e['x']},{e['y']}) {bar}")
        db.close()
        return

    target_profiles = profiles
    if args.device:
        target_profiles = [p for p in profiles if args.device in p["id"]]
        if not target_profiles:
            print(f"No device matching '{args.device}' found.")
            db.close()
            return

    for p in target_profiles:
        print_device_report(db, p["id"])

    print_recent_corrections(db, args.device)
    db.close()


if __name__ == "__main__":
    main()
