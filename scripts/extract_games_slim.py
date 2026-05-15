"""Distil the games-manager API dump into a reviewable slim view.

The source `games-api.md` is multi-megabyte (every prod game, with multi-size
image URLs and provider metadata we don't need). This script reads it once,
strips any markdown fences if present, parses the JSON, and writes:

  - `data/games_slim.json`  — one object per game with only the fields we
    care about for `game_directory` design (id/code/aggregator/type/category/
    name/description/hexColor/status/minBet/maxBet/rtp/liveDealer/flags).
  - stdout summary — counts by type/category/aggregator/provider/status so
    the operator can see the taxonomy at a glance.

Usage:
    uv run scripts/extract_games_slim.py [path-to-games-api.md]

The default input path is `games-api.md` in the repo root. Output goes to
`data/games_slim.json` (overwritten on each run).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path


_DEFAULT_INPUT = "games-api.json"
_DEFAULT_OUTPUT = "data/games_slim.json"

# Fields we pull through verbatim — the user-named set (aggregator, type,
# name, description, hex, state) plus a few that the game_directory schema
# will need.
_FIELDS = (
    "id",
    "code",
    "extGameId",
    "provider",
    "aggregator",
    "type",
    "category",
    "name",
    "description",
    "hexColor",
    "status",
    "jurisdictionCode",
    "minBet",
    "maxBet",
    "rtp",
    "liveDealer",
    "supportJackpots",
    "supportFreeSpins",
    "orientation",
    "bonusEnabled",
    "tagLine",
)


def _load_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip markdown fences if the file is wrapped in ```json ... ```.
    if "```" in text:
        # Take the largest fenced block (the JSON one); fall through to raw
        # parse if that fails.
        chunks = text.split("```")
        # Look for chunks that start with json/JSON or look like JSON.
        for chunk in sorted(chunks, key=len, reverse=True):
            cleaned = chunk.lstrip()
            if cleaned.startswith(("json\n", "JSON\n")):
                cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
    # Direct JSON file
    return json.loads(text)


def _slim_game(g: dict) -> dict:
    out = {k: g.get(k) for k in _FIELDS}
    # description: trim to keep slim file readable.
    if isinstance(out.get("description"), str) and len(out["description"]) > 200:
        out["description"] = out["description"][:200] + "…"
    return out


def main(argv: list[str]) -> int:
    input_path = Path(argv[1]) if len(argv) > 1 else Path(_DEFAULT_INPUT)
    if not input_path.exists():
        print(f"input not found: {input_path}", file=sys.stderr)
        return 1

    print(f"reading {input_path} ({input_path.stat().st_size // 1024} KB)…")
    payload = _load_json(input_path)

    games = payload.get("games") if isinstance(payload, dict) else payload
    if not isinstance(games, list):
        print(f"unexpected payload shape — top-level 'games' not a list", file=sys.stderr)
        return 2

    slim = [_slim_game(g) for g in games if isinstance(g, dict)]
    out_path = Path(_DEFAULT_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(slim, indent=2, sort_keys=False), encoding="utf-8")
    print(f"wrote {len(slim)} games to {out_path} ({out_path.stat().st_size // 1024} KB)")

    # ── Summary stats ──────────────────────────────────────────────────
    def _counts(field: str, top: int = 20) -> list:
        c = Counter(g.get(field) for g in slim)
        return c.most_common(top)

    print()
    print("=== status ===")
    for v, n in _counts("status"):
        print(f"  {n:5d}  {v}")
    print()
    print("=== type (top 20) ===")
    for v, n in _counts("type"):
        print(f"  {n:5d}  {v}")
    print()
    print("=== category (top 20) ===")
    for v, n in _counts("category"):
        print(f"  {n:5d}  {v}")
    print()
    print("=== aggregator (top 10) ===")
    for v, n in _counts("aggregator", top=10):
        print(f"  {n:5d}  {v}")
    print()
    print("=== provider (top 15) ===")
    for v, n in _counts("provider", top=15):
        print(f"  {n:5d}  {v}")
    print()
    print("=== jurisdictionCode ===")
    for v, n in _counts("jurisdictionCode"):
        print(f"  {n:5d}  {v}")
    print()
    print("=== orientation ===")
    for v, n in _counts("orientation"):
        print(f"  {n:5d}  {v}")
    print()
    print(f"=== flags (n={len(slim)}) ===")
    print(f"  liveDealer=True:        {sum(1 for g in slim if g.get('liveDealer'))}")
    print(f"  supportJackpots=True:   {sum(1 for g in slim if g.get('supportJackpots'))}")
    print(f"  supportFreeSpins=True:  {sum(1 for g in slim if g.get('supportFreeSpins'))}")
    print(f"  bonusEnabled=True:      {sum(1 for g in slim if g.get('bonusEnabled'))}")

    # Surface the FanCash Spins / Spin to Win entry specifically — the demo
    # target. Match by name substring (case-insensitive).
    print()
    print("=== FanCash Spins / Spin to Win matches ===")
    needles = ("fancash spins", "spin to win", "spin2win", "fancash spin")
    matches = [
        g for g in slim
        if isinstance(g.get("name"), str)
        and any(n in g["name"].lower() for n in needles)
    ]
    if not matches:
        print("  (none found by name substring — needs separate lookup)")
    for m in matches:
        print(f"  {m['code']} | {m['name']} | type={m['type']} category={m['category']} status={m['status']}")

    print()
    print("=== blackjack matches (for T052 demo) ===")
    bj = [g for g in slim if isinstance(g.get("category"), str) and "blackjack" in g["category"].lower()]
    bj_by_type = [g for g in slim if isinstance(g.get("type"), str) and "blackjack" in g["type"].lower()]
    bj = bj or bj_by_type
    for m in bj[:15]:
        print(f"  {m['code']} | {m['name']} | type={m['type']} category={m['category']} status={m['status']}")
    print(f"  …(total: {len(bj)})")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
