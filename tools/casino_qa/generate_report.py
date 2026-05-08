import os
from datetime import datetime


def _slugify(name: str) -> str:
    """Lowercase + alnum/dash only — for report filenames."""
    out = []
    for ch in (name or "session").lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "session"


def generate_report(args: dict) -> dict:
    """Generate a structured QA test session report.

    Per SOUL §6, reports go to `reports/YYYY-MM-DD-{game-slug}-session.md`.

    Args:
        starting_balance: Balance before game (e.g. "$50.00")
        ending_balance: Balance after game (e.g. "$49.80")
        spins_played: Number of spins completed
        total_spins: Expected spins (default 5)
        wilds: Number of wilds encountered
        super_wilds: Number of super wilds encountered
        extra_spins_purchased: Must be 0 for PASS
        anomalies: List of anomaly descriptions
        run_id: Test run identifier (used for filename uniqueness if multiple per day)
        game_name: Game played (for filename slug, default "slingo-cash-eruption")
        observations: Optional list of UX/QA observations (non-bug)
        bugs: Optional list of {severity, summary, repro?, screenshot?} dicts
    """
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

    # Calculate delta
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
