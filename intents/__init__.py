"""Intent registry — load, validate, and serve all intent_*.md files at startup.

A new intent is added by dropping a markdown file in this directory; no Python
edit is required. Files prefixed with `_` are skipped (use to temporarily disable).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from intents.base import IntentDeclaration, RiskTier

log = logging.getLogger(__name__)

_VALID_RISK_TIERS = {"HIGH", "MEDIUM", "LOW"}
_BODY_TOKEN_BUDGET = 600  # SC-012 — operational soul only


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file's YAML frontmatter from its body.

    Returns ({}, full_text) if no frontmatter is present.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e
    body = parts[2].lstrip("\n")
    return fm, body


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 4 chars per token. Fine for the 600-token budget guard."""
    return max(1, len(text) // 4)


def _validate(decl: IntentDeclaration, filename_stem: str) -> List[str]:
    """Return a list of validation warnings. An empty list means the intent is fine."""
    warnings: List[str] = []
    if not decl.id:
        warnings.append("missing id")
    elif decl.id != filename_stem:
        warnings.append(f"id '{decl.id}' does not match filename stem '{filename_stem}'")
    if not decl.id.startswith("intent_"):
        warnings.append(f"id '{decl.id}' must start with 'intent_'")
    if not decl.end_state_signatures:
        warnings.append("end_state_signatures must be non-empty")
    if not decl.success_check:
        warnings.append("success_check must be non-empty")
    if decl.risk_tier not in _VALID_RISK_TIERS:
        warnings.append(f"risk_tier '{decl.risk_tier}' must be one of {sorted(_VALID_RISK_TIERS)}")
    if decl.body_token_estimate > _BODY_TOKEN_BUDGET:
        warnings.append(
            f"body is ~{decl.body_token_estimate} tokens, over the {_BODY_TOKEN_BUDGET}-token budget (SC-012)"
        )
    return warnings


def _parse_one(path: Path) -> tuple[Optional[IntentDeclaration], List[str]]:
    """Parse a single intent file. Returns (declaration|None, warnings)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, [f"cannot read {path}: {e}"]
    try:
        fm, body = _split_frontmatter(text)
    except ValueError as e:
        return None, [str(e)]

    decl = IntentDeclaration(
        id=str(fm.get("id", "")),
        end_state_signatures=list(fm.get("end_state_signatures") or []),
        success_check=str(fm.get("success_check") or ""),
        guardrails=list(fm.get("guardrails") or []),
        risk_tier=str(fm.get("risk_tier", "LOW")).upper(),  # type: ignore[arg-type]
        notes=fm.get("notes"),
        body_md=body,
        body_token_estimate=_estimate_tokens(body),
        source_path=str(path),
    )
    warnings = _validate(decl, path.stem)
    return decl, warnings


def load_registry(intents_dir: Optional[str] = None) -> Dict[str, IntentDeclaration]:
    """Load all intent_*.md files at startup. Idempotent.

    Files starting with `_` are skipped. Files with critical validation errors
    (missing id / non-matching filename / non-`intent_` prefix / empty end-state)
    are excluded; warnings are logged but startup continues. Token-budget warnings
    do NOT exclude the intent — the file still loads.
    """
    base = Path(intents_dir) if intents_dir else Path(__file__).parent
    registry: Dict[str, IntentDeclaration] = {}
    for path in sorted(base.glob("*.md")):
        if path.name.startswith("_"):
            continue
        decl, warnings = _parse_one(path)
        if decl is None:
            log.warning("intent registry: skipping %s — %s", path.name, "; ".join(warnings))
            continue
        # Hard-fail conditions: must have id, end-state, success_check
        hard_fail = [
            w for w in warnings
            if any(s in w for s in ("missing id", "must start with", "must be non-empty",
                                     "does not match filename stem"))
        ]
        if hard_fail:
            log.warning("intent registry: skipping %s — %s", path.name, "; ".join(hard_fail))
            continue
        if decl.id in registry:
            log.warning(
                "intent registry: duplicate id '%s' in %s (already loaded from %s)",
                decl.id, path, registry[decl.id].source_path,
            )
            continue
        for w in warnings:
            log.warning("intent registry: %s — %s", path.name, w)
        registry[decl.id] = decl
    log.info(
        "intent registry: %d intents loaded (%s)",
        len(registry),
        ", ".join(sorted(registry.keys())) or "none",
    )
    return registry


__all__ = ["IntentDeclaration", "RiskTier", "load_registry"]
