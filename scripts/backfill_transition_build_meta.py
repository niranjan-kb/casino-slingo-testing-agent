"""One-shot backfill for `build_env` and `app_package` columns added by spec 004.

Existing seeded transitions / signatures / elements have `build_env='unknown'`
after the additive ALTER. For rows verified within the staleness window, we
bump them to the active worker's BUILD_ENV / APP_PACKAGE so read-time decay
(shared/screen_graph._effective_confidence) treats them as still-valid for
this build. Older rows keep `unknown` and the decay model treats them as
exploratory (R5/R6).

Usage:
    BUILD_ENV=test APP_PACKAGE=com.betfanatics.casino.test \
        uv run scripts/backfill_transition_build_meta.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

from shared.screen_map_db import ScreenMapDB

_TABLES = ("screen_signatures", "screen_elements", "screen_transitions")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report counts only; do not update")
    parser.add_argument("--window-days", type=int, default=30,
                        help="rows verified within this window get backfilled (default 30)")
    parser.add_argument("--build-env", default=os.getenv("BUILD_ENV", ""),
                        help="value for build_env (defaults to $BUILD_ENV)")
    parser.add_argument("--app-package", default=os.getenv("APP_PACKAGE", ""),
                        help="value for app_package (defaults to $APP_PACKAGE)")
    args = parser.parse_args()

    if not args.build_env or not args.app_package:
        print("ERROR: build_env and app_package must be set (env or --flag).", file=sys.stderr)
        return 2

    db = ScreenMapDB()
    cutoff = (datetime.utcnow() - timedelta(days=args.window_days)).isoformat()
    conn = db._get_conn()

    print(f"Backfilling rows verified after {cutoff} -> "
          f"build_env='{args.build_env}', app_package='{args.app_package}'")
    if args.dry_run:
        print("DRY RUN — no writes will be performed.")

    total_updated = 0
    for table in _TABLES:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "build_env" not in cols or "app_package" not in cols:
            print(f"  {table}: skip (missing build_env/app_package columns)")
            continue
        # Only SCREEN_TRANSITIONS and SCREEN_ELEMENTS have last_verified.
        # screen_signatures has no timestamp; backfill all 'unknown' rows for it
        # since we have no way to filter by recency.
        if "last_verified" in cols:
            cnt_q = (f"SELECT COUNT(*) FROM {table} "
                     f"WHERE build_env='unknown' AND last_verified IS NOT NULL "
                     f"AND last_verified >= ?")
            params = (cutoff,)
        else:
            cnt_q = f"SELECT COUNT(*) FROM {table} WHERE build_env='unknown'"
            params = ()
        cnt = conn.execute(cnt_q, params).fetchone()[0]
        print(f"  {table}: {cnt} 'unknown' rows match the window")
        if cnt and not args.dry_run:
            if "last_verified" in cols:
                conn.execute(
                    f"UPDATE {table} SET build_env=?, app_package=? "
                    f"WHERE build_env='unknown' AND last_verified IS NOT NULL "
                    f"AND last_verified >= ?",
                    (args.build_env, args.app_package, cutoff),
                )
            else:
                conn.execute(
                    f"UPDATE {table} SET build_env=?, app_package=? "
                    f"WHERE build_env='unknown'",
                    (args.build_env, args.app_package),
                )
            total_updated += cnt
    if not args.dry_run:
        conn.commit()
        print(f"OK — {total_updated} rows updated total")
    else:
        print("(dry run — no rows updated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
