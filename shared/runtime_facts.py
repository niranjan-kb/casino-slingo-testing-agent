"""RuntimeFacts envelope — what the agent knows at the start of a casino visit.

Per spec 005 anti-hardcoding inventory (plan.md §"Anti-hardcoding inventory"):
credentials, OTP source, app id, resolution, jurisdiction, and budget bounds
are NOT prose-baked into goal prompts. They live here as a structured JSON
envelope, loaded once at workflow start, threaded through every activity that
needs them.

The envelope's role in the layered prompt assembly (setup-doc §5):
    L3 runtime facts: this dataclass, JSON-serialised, ~400 tokens.

Hard ceiling rule (FR-003 / FR-004): MAX_LOSS_USD env is the hard cap; prompts
can only lower it via `lower_budget()`, which silently clamps to ≤ env value.
The agent cannot raise its own bankroll cap.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DeviceFacts:
    """Discovered device characteristics. Sourced from `select_device` MCP call."""

    platform: str  # android | ios | web
    profile: str  # e.g. "android-1080x1920"
    resolution: str  # WxH
    dpi: Optional[int] = None
    locale: str = "en-US"
    currency: str = "USD"


@dataclass(frozen=True)
class TargetFacts:
    """What the agent is logging into. App id and version come from select_device,
    NEVER from a hardcoded convention. Account refs and OTP sources are env handles
    that resolve to a secret store at activity time — secrets never enter the
    workflow input or any prompt."""

    app_id: str  # com.betfanatics.casino.cert | com.betfanatics.Casino.cert | casino.cert.betfanatics.com
    build_env: str  # dev | test | cert | prod-debug | prod
    app_version: str = "unknown"
    account_ref: Optional[str] = None  # opaque handle into secret store
    otp_source: Optional[str] = None  # "static:NNNNNN" | "imap:test_inbox" | "sms:provider"


@dataclass(frozen=True)
class BudgetConstraints:
    """Stop-loss + per-session bounds. Env is the hard ceiling; prompts can only
    lower (FR-003). Defaults for vague prompts (FR-004): max_spins=20, max_minutes=10."""

    max_loss_usd: float
    max_spins: int = 20
    max_minutes: int = 10
    write_allowed: bool = True  # false in prod read-only spectator mode


@dataclass(frozen=True)
class RuntimeFacts:
    """The full envelope. Loaded once at workflow start; injected as L3 in the
    layered prompt assembly. Frozen so accidental mutation is a hard error."""

    session_id: str
    platform: str
    build_env: str
    device: DeviceFacts
    target: TargetFacts
    constraints: BudgetConstraints
    jurisdiction: Optional[str] = None  # NJ | PA | MI | WV | ...
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        """Serialise for the L3 prompt layer. Stable shape for prompt-cache hits."""
        return asdict(self)


class RuntimeFactsError(RuntimeError):
    """Raised when required RuntimeFacts cannot be derived. Fail loud rather than
    fall back to a hardcoded convention — the no-hardcoding mandate is structural."""


def load_runtime_facts(
    *,
    session_id: str,
    select_device_result: Optional[Dict[str, Any]] = None,
) -> RuntimeFacts:
    """Build RuntimeFacts from env + (optionally) a select_device MCP result.

    Env provides policy facts (BUILD_ENV, MAX_LOSS_USD, JURISDICTION, ACCOUNT_REF,
    OTP_SOURCE). select_device provides discovered device facts (resolution, dpi,
    app_id, app_version). The split is deliberate: nothing about a specific build
    or device is baked into code.

    APP_PACKAGE env may override or supply app_id when select_device is unavailable
    (e.g. during workflow startup before first MCP call). If neither is present,
    raises RuntimeFactsError rather than falling back to a hardcoded convention.
    """
    build_env = os.environ.get("BUILD_ENV") or _required("BUILD_ENV")
    platform_env = os.environ.get("PLATFORM") or _required("PLATFORM")

    sd = select_device_result or {}
    platform = sd.get("platform") or platform_env
    resolution = sd.get("resolution") or os.environ.get("DEVICE_RESOLUTION") or _required(
        "DEVICE_RESOLUTION (or select_device.resolution)"
    )
    dpi = sd.get("dpi")
    profile = sd.get("profile") or f"{platform}-{resolution}"
    app_version = sd.get("app_version", "unknown")
    app_id = sd.get("app_id") or os.environ.get("APP_PACKAGE")
    if not app_id:
        raise RuntimeFactsError(
            "app_id missing: provide via select_device MCP call or APP_PACKAGE env. "
            "App id is build-env specific and MUST NOT be hardcoded."
        )

    device = DeviceFacts(
        platform=platform,
        profile=profile,
        resolution=resolution,
        dpi=dpi,
        locale=os.environ.get("LOCALE", "en-US"),
        currency=os.environ.get("CURRENCY", "USD"),
    )

    target = TargetFacts(
        app_id=app_id,
        build_env=build_env,
        app_version=app_version,
        account_ref=os.environ.get("ACCOUNT_REF") or None,
        otp_source=os.environ.get("OTP_SOURCE") or None,
    )

    max_loss_usd = _read_float("MAX_LOSS_USD", required=True)
    constraints = BudgetConstraints(
        max_loss_usd=max_loss_usd,
        max_spins=_read_int("DEFAULT_MAX_SPINS", default=20),
        max_minutes=_read_int("DEFAULT_MAX_MINUTES", default=10),
        write_allowed=build_env != "prod",
    )

    return RuntimeFacts(
        session_id=session_id,
        platform=platform,
        build_env=build_env,
        device=device,
        target=target,
        constraints=constraints,
        jurisdiction=os.environ.get("JURISDICTION") or None,
    )


def lower_budget(
    facts: RuntimeFacts,
    *,
    max_loss_usd: Optional[float] = None,
    max_spins: Optional[int] = None,
    max_minutes: Optional[int] = None,
) -> RuntimeFacts:
    """Apply a prompt-supplied budget. STRICTER ONLY (FR-003, FR-004).

    A request to *raise* a bound is silently clamped to the existing value. The
    agent cannot raise its own stop-loss, max-spins, or max-minutes — only the
    operator can, via env vars at worker start.

    Returns a new (frozen) RuntimeFacts; the original is unchanged.
    """
    c = facts.constraints
    new = BudgetConstraints(
        max_loss_usd=min(c.max_loss_usd, max_loss_usd) if max_loss_usd is not None else c.max_loss_usd,
        max_spins=min(c.max_spins, max_spins) if max_spins is not None else c.max_spins,
        max_minutes=min(c.max_minutes, max_minutes) if max_minutes is not None else c.max_minutes,
        write_allowed=c.write_allowed,
    )
    return RuntimeFacts(
        session_id=facts.session_id,
        platform=facts.platform,
        build_env=facts.build_env,
        device=facts.device,
        target=facts.target,
        constraints=new,
        jurisdiction=facts.jurisdiction,
        extras=dict(facts.extras),
    )


def _required(name: str) -> str:
    raise RuntimeFactsError(
        f"required env var {name} not set; cannot construct RuntimeFacts. "
        "Anti-hardcoding mandate: no per-build or per-device fallbacks in code."
    )


def _read_float(name: str, default: Optional[float] = None, *, required: bool = False) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        if required:
            raise RuntimeFactsError(f"required env var {name} not set")
        if default is None:
            raise RuntimeFactsError(f"env {name} unset and no default")
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeFactsError(f"env {name}={raw!r} is not a number") from exc


def _read_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeFactsError(f"env {name}={raw!r} is not an integer") from exc
