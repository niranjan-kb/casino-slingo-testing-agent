"""Intent declaration dataclass.

An Intent is a thin, declarative unit: an end-state (set of screen signatures
the agent is trying to land on), a success check, and any guardrails. The
markdown body is the operational soul — what the LLM reads each turn the
intent is active. Procedure (tools, selectors, fallbacks, wait-tables) lives
in the screen-map and tool catalog, never here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional


RiskTier = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class IntentDeclaration:
    id: str
    end_state_signatures: List[str]
    success_check: str
    guardrails: List[str] = field(default_factory=list)
    risk_tier: RiskTier = "LOW"
    notes: Optional[str] = None
    body_md: str = ""
    body_token_estimate: int = 0
    source_path: Optional[str] = None
