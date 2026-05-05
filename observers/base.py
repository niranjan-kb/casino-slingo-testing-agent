"""Type contracts for the observer framework.

Observers piggyback on data the goal already pulled (page-source XML,
screen signature, tool-result metadata, persona dials, recent
observation history) and emit structured observations into the
session report. They are a side-channel — zero extra device round-trips.

Engines are CODE (written once, in observers/engines/), observers are
DATA (one YAML + acceptance.md per feature, in observers/<id>/).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable
from xml.etree.ElementTree import Element


Severity = Literal["info", "warn", "bug"]
PassFail = Literal["pass", "fail", "n/a"]


@dataclass
class PersonaDialsView:
    """Read-only view of the persona dials handed to every observer tick.

    The full PersonaDials lives in observers.persona; this is the subset
    that observer YAML expressions are allowed to reference.
    """

    curiosity: str = "high"           # "high" | "low"
    risk_appetite: str = "low"        # "low" | "med" | "high"
    jackpot_optin: bool = True
    max_session_loss_usd: float = 5.0
    react_to_wins: bool = True
    explore_unknown_icons: bool = True


@dataclass
class ScreenContext:
    """Curated input bundle handed to every observer per tick.

    Built once per device-affecting tool result and reused by all
    observers in that tick. Observers MUST NOT pull additional device
    data — they work from this bundle only (FR-008).
    """

    page_source_xml: Optional[Element]              # parsed page-source root
    screen_signature: str                           # computed signature
    screen_id: Optional[str]                        # known signature → id, else None
    novelty: bool                                   # first-seen this run
    persona: PersonaDialsView
    last_tool_name: Optional[str]
    last_tool_args: Dict[str, Any]
    last_tool_success: bool
    last_tool_error: Optional[str]
    balance_snapshot: Dict[str, Any]                # parsed wallet/balance, may be empty
    recent_observations: List["ObservationResult"]  # last N for de-dup
    run_id: str
    goal_id: str


@dataclass
class ObservationResult:
    """The structured output of one observer firing on one tick."""

    observer_id: str
    matched: bool
    severity: Severity = "info"
    summary: str = ""
    evidence_path: Optional[str] = None
    spec_link: Optional[str] = None
    pass_fail: PassFail = "n/a"
    auto_handle: bool = False
    sub_flow_tools: List[Dict[str, Any]] = field(default_factory=list)
    captured: Dict[str, Any] = field(default_factory=dict)
    failed_rule: Optional[str] = None               # populated when pass_fail == "fail"
    recheck_after_s: Optional[float] = None         # request a delayed re-check
    screen_signature: Optional[str] = None          # signature at time of observation
    screen_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observer_id": self.observer_id,
            "matched": self.matched,
            "severity": self.severity,
            "summary": self.summary,
            "evidence_path": self.evidence_path,
            "spec_link": self.spec_link,
            "pass_fail": self.pass_fail,
            "auto_handle": self.auto_handle,
            "sub_flow_tools": list(self.sub_flow_tools),
            "captured": dict(self.captured),
            "failed_rule": self.failed_rule,
            "recheck_after_s": self.recheck_after_s,
            "screen_signature": self.screen_signature,
            "screen_id": self.screen_id,
        }


@runtime_checkable
class Observer(Protocol):
    """An observer is a declarative unit of feature awareness.

    Concrete observers are produced by an ObserverEngine reading a YAML
    + acceptance.md pair in observers/<feature_id>/. Engines are
    written once in observers/engines/; observer YAMLs are written
    per feature.
    """

    id: str
    spec_url: Optional[str]
    severity_on_fail: Severity

    def trigger(self, ctx: ScreenContext) -> bool: ...

    def verify(self, ctx: ScreenContext) -> ObservationResult: ...

    def sub_flow(self, ctx: ScreenContext) -> List[Dict[str, Any]]: ...
