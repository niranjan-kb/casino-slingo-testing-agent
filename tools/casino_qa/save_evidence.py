import os
import shutil
from datetime import datetime


def save_evidence(args: dict) -> dict:
    """Save a screenshot as labeled test evidence.

    Copies the latest screenshot to the evidence directory with a descriptive label.

    Args:
        screenshot_path: Path to the screenshot file (from appium_screenshot result)
        label: Descriptive label (e.g. "pre_game_balance", "spin_3_wild", "post_exit")
        run_id: Optional test run identifier (defaults to timestamp)
    """
    screenshot_path = args.get("screenshot_path", "")
    label = args.get("label", "unlabeled")
    run_id = args.get("run_id", datetime.now().strftime("%Y%m%d_%H%M%S"))

    if not screenshot_path or not os.path.exists(screenshot_path):
        return {"status": "error", "error": f"Screenshot not found: {screenshot_path}"}

    evidence_dir = os.path.join(os.getcwd(), "evidence", run_id)
    os.makedirs(evidence_dir, exist_ok=True)

    ext = os.path.splitext(screenshot_path)[1] or ".png"
    timestamp = datetime.now().strftime("%H%M%S")
    dest = os.path.join(evidence_dir, f"{timestamp}_{label}{ext}")
    shutil.copy2(screenshot_path, dest)

    return {
        "status": "success",
        "evidence_path": dest,
        "label": label,
        "run_id": run_id,
    }
