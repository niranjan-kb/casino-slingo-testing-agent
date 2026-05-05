"""Persona dials — single configuration per session, loaded from YAML.

The dials gate observer sub-flow execution and inform goal-level risk
choices. They are DATA, not prompt — change them by editing
prompts/persona/persona_dials.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import yaml

from observers.base import PersonaDialsView


_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "prompts",
    "persona",
    "persona_dials.yaml",
)


@dataclass
class PersonaDials:
    """Full persona configuration for one session."""

    curiosity: str = "high"
    risk_appetite: str = "low"
    jackpot_optin: bool = True
    max_session_loss_usd: float = 5.0
    react_to_wins: bool = True
    explore_unknown_icons: bool = True
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PersonaDials":
        clean = dict(data or {})
        return cls(
            curiosity=str(clean.get("curiosity", "high")).lower(),
            risk_appetite=str(clean.get("risk_appetite", "low")).lower(),
            jackpot_optin=bool(clean.get("jackpot_optin", True)),
            max_session_loss_usd=float(clean.get("max_session_loss_usd", 5.0)),
            react_to_wins=bool(clean.get("react_to_wins", True)),
            explore_unknown_icons=bool(clean.get("explore_unknown_icons", True)),
            raw=clean,
        )

    def view(self) -> PersonaDialsView:
        """Return the read-only view passed to observer ticks."""
        return PersonaDialsView(
            curiosity=self.curiosity,
            risk_appetite=self.risk_appetite,
            jackpot_optin=self.jackpot_optin,
            max_session_loss_usd=self.max_session_loss_usd,
            react_to_wins=self.react_to_wins,
            explore_unknown_icons=self.explore_unknown_icons,
        )


def load_persona_dials(path: Optional[str] = None) -> PersonaDials:
    """Load persona dials from YAML. Returns defaults on missing file."""
    target = path or _DEFAULT_PATH
    if not os.path.exists(target):
        return PersonaDials()
    with open(target) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return PersonaDials()
    return PersonaDials.from_dict(data)
