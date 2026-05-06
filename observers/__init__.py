"""Observer framework — package entry point.

Observers piggyback on data the goal already pulled (page-source XML,
screen signature, tool-result metadata, persona dials, recent
observation history) and emit structured observations into the
session report. Side-channel: zero extra device round-trips.

Layout:
- observers/base.py            Type contracts (ScreenContext, ObservationResult, Observer).
- observers/persona.py         PersonaDials loader (YAML in prompts/persona/).
- observers/engines/  (phase 1+) Generic ObserverEngines (Modal, Toast, BadgeState,
                                 BalanceDelta, Novelty, ToolError) — CODE, written once.
- observers/<feature_id>/      observer.yaml + acceptance.md per feature — DATA.

Adding a new feature observer is a YAML + AC change, not Python (FR-002).

v1 phase 0 ships only the type contracts and registry. Engines and the
auto-discovery loader land in phase 1.
"""

from typing import List

from observers.base import (
    ObservationResult,
    Observer,
    PassFail,
    PersonaDialsView,
    ScreenContext,
    Severity,
)


# Module-level registry. Engines/loader populate this at import time
# in later phases. Phase 0 ships an empty registry — wiring only.
REGISTRY: List[Observer] = []


def register(obs: Observer) -> None:
    """Add an observer to the global registry. Idempotent on observer.id."""
    for existing in REGISTRY:
        if existing.id == obs.id:
            return
    REGISTRY.append(obs)


def tick(ctx: ScreenContext) -> List[ObservationResult]:
    """Run every registered observer's trigger/verify against ctx.

    Per FR-022: observer exceptions MUST NOT propagate. Any failure is
    recorded as a warn-severity observation describing the crash and the
    pass continues.
    """
    results: List[ObservationResult] = []
    for obs in REGISTRY:
        try:
            if not obs.trigger(ctx):
                continue
            r = obs.verify(ctx)
            if r.matched and r.auto_handle:
                try:
                    r.sub_flow_tools = obs.sub_flow(ctx)
                except Exception as e:                              # noqa: BLE001
                    r.severity = "warn"
                    crash_note = f"sub_flow crashed: {e}"
                    r.summary = f"{r.summary} | {crash_note}".strip(" |")
                    r.sub_flow_tools = []
            results.append(r)
        except Exception as e:                                      # noqa: BLE001
            results.append(
                ObservationResult(
                    observer_id=getattr(obs, "id", "<unknown>"),
                    matched=False,
                    severity="warn",
                    summary=f"observer crashed: {e}",
                )
            )
    return results


__all__ = [
    "ObservationResult",
    "Observer",
    "PassFail",
    "PersonaDialsView",
    "REGISTRY",
    "ScreenContext",
    "Severity",
    "register",
    "tick",
]


# Auto-register the v1 observers via import side-effects. Adding a new
# observer module here is the equivalent of adding a YAML in the future
# spec-attached architecture — the framework discovers it at import time.
from observers import unknown_screen as _unknown_screen  # noqa: E402, F401
