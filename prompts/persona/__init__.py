"""Shared agent persona — soul + identity loaded by every goal.

Goals are platform-agnostic capabilities. Persona is the single voice across all goals.
Each goal composes its own user.md / tools.md on top of these.
"""

import os
from typing import Dict


_PERSONA_DIR = os.path.dirname(__file__)


def load(filename: str) -> str:
    """Read a markdown file from the shared persona directory."""
    path = os.path.join(_PERSONA_DIR, filename)
    with open(path) as f:
        return f.read()


def render(text: str, env: Dict[str, str]) -> str:
    """Replace {{KEY}} placeholders in text from the env dict."""
    for k, v in env.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def env_context() -> Dict[str, str]:
    """Compute the standard env-variable substitution map used by every goal."""
    build_env = (os.getenv("BUILD_ENV", "dev") or "dev").strip().lower()
    default_otp = (os.getenv("DEFAULT_OTP", "") or "").strip()

    if build_env in {"dev", "test"} and default_otp:
        otp_policy = (
            f"AUTO-OTP: BUILD_ENV is `{build_env}`. Use the fixed OTP `{default_otp}` "
            "WITHOUT asking the user. Type it directly into the OTP input."
        )
    else:
        otp_policy = (
            f"ASK-USER-OTP: BUILD_ENV is `{build_env}`. Ask the user for the OTP "
            "via SMS (`next='question'`) and wait for their reply."
        )

    explicit_pkg = os.getenv("APP_PACKAGE")
    if explicit_pkg:
        app_package = explicit_pkg
    elif build_env in {"dev", "test", "cert"}:
        app_package = f"com.betfanatics.casino.{build_env}"
    else:
        app_package = "com.betfanatics.casino"

    return {
        "ANDROID_SERIAL": os.getenv("ANDROID_SERIAL", "emulator-5554"),
        "DEVICE_RESOLUTION": os.getenv("DEVICE_RESOLUTION", "1344x2992"),
        "APP_PACKAGE": app_package,
        "BUILD_ENV": build_env,
        "PRODUCT_FLAVOR": os.getenv("PRODUCT_FLAVOR", "casino"),
        "PLATFORM": os.getenv("PLATFORM", "android"),
        "TEST_EMAIL": os.getenv("TEST_EMAIL", "not configured"),
        "TEST_PASSWORD": os.getenv("TEST_PASSWORD", ""),
        "TEST_PASSWORD_STATUS": "configured" if os.getenv("TEST_PASSWORD") else "not configured",
        "DEFAULT_OTP": default_otp or "<not configured>",
        "OTP_POLICY": otp_policy,
    }


def soul_and_identity() -> str:
    """Return the rendered persona (soul + identity) ready to prepend to a goal's prompt."""
    env = env_context()
    soul = render(load("soul.md"), env)
    identity = render(load("identity.md"), env)
    return soul + "\n\n---\n\n" + identity
