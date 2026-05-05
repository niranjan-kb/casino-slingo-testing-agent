"""Screen identity computation for the observer framework.

Reuses the matching logic from tools/slingo_qa/detect_screen.py to derive
a stable screen identity from page-source XML, without making any extra
device calls (FR-008).

Used by the run_observers activity to assign novelty keys per real
screen identity, not per content hash. Two outcomes per tick:

  matched   → screen_id="fanatics_one_email", novelty_key=screen_id
              (de-dup is by screen identity across runs and devices)
  unmatched → screen_id=None,  novelty_key="unk:<hash-of-resource-ids>"
              (still stable for the same unknown screen across devices,
              so the report shows a single row per unknown screen)
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple


# Confidence threshold for treating a screen as matched. Below this, the
# screen is treated as unknown and gets a stable hash signature instead.
DEFAULT_MATCH_THRESHOLD = 0.4


# ── Page-source extraction ──────────────────────────────────────────────


def extract_xml_text(tool_result: Any) -> str:
    """Pull the raw page-source XML string out of an arbitrary tool result.

    The MCP appium server wraps the XML in a markdown fence and HTML-escapes
    it. The Slingo QA tools (DetectScreen) already account for this; we
    mirror the unwrap here so observers can read XML straight from the
    workflow's last tool result.

    Tolerant of:
      - dict with `content` as str  (most appium calls)
      - dict with `content` as list (MCP CallToolResult-like)
      - already-extracted XML string
      - empty / non-XML payloads (returns "")
    """
    if isinstance(tool_result, str):
        raw = tool_result
    elif isinstance(tool_result, dict):
        c = tool_result.get("content")
        if isinstance(c, str):
            raw = c
        elif isinstance(c, list):
            raw = ""
            for item in c:
                if isinstance(item, dict):
                    raw += str(item.get("text") or "")
                else:
                    raw += getattr(item, "text", str(item))
        else:
            raw = ""
    else:
        return ""
    return raw or ""


def parse_page_source(raw: str) -> List[Dict[str, Any]]:
    """Convert raw page-source XML text into a flat list of element dicts."""
    if not raw:
        return []
    raw = (
        raw.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )
    m = re.search(r"<\?xml.*?</hierarchy>", raw, re.DOTALL)
    if not m:
        return []
    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return []
    elements: List[Dict[str, Any]] = []
    for node in root.iter():
        attrs = node.attrib
        text = (attrs.get("text") or "").strip()
        res_id = attrs.get("resource-id") or ""
        desc = attrs.get("content-desc") or ""
        bounds = attrs.get("bounds") or ""
        if not (text or res_id or desc):
            continue
        elements.append(
            {
                "text": text,
                "resource-id": res_id,
                "content-desc": desc,
                "class": attrs.get("class", ""),
                "bounds": bounds,
            }
        )
    return elements


# ── Signature matching ──────────────────────────────────────────────────


def match_screen(
    elements: List[Dict[str, Any]],
    signatures: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Optional[str], float, List[str]]:
    """Match a list of element dicts against seeded screen_signatures.

    Returns (screen_name or None, confidence in [0,1], matched-signature
    descriptors). Mirrors detect_screen.py:_match_signatures so observer
    matching stays consistent with the goal-side detector.
    """
    found_texts = set()
    found_ids = set()
    for elem in elements:
        text = (elem.get("text") or "").strip()
        if text:
            found_texts.add(text)
        res_id = elem.get("resource-id") or ""
        if res_id:
            short_id = res_id.split("/")[-1] if "/" in res_id else res_id
            found_ids.add(short_id)
            found_ids.add(res_id)

    best_screen: Optional[str] = None
    best_score = 0.0
    best_matched: List[str] = []
    for screen_name, sigs in signatures.items():
        score = 0
        matched: List[str] = []
        max_possible = sum(s["priority"] for s in sigs)
        for sig in sigs:
            sig_type = sig["signature_type"]
            sig_value = sig["signature_value"]
            hit = False
            if sig_type == "element_text":
                hit = any(sig_value.lower() in t.lower() for t in found_texts)
            elif sig_type == "element_id":
                hit = any(sig_value.lower() in i.lower() for i in found_ids)
            if hit:
                score += sig["priority"]
                matched.append(f"{sig_type}:{sig_value}")
        confidence = min(score / max(max_possible, 1), 1.0)
        if confidence > best_score:
            best_score = confidence
            best_screen = screen_name
            best_matched = matched
    return best_screen, best_score, best_matched


def stable_unknown_signature(elements: List[Dict[str, Any]]) -> str:
    """Compute a stable hash for an unknown screen.

    Uses the sorted set of short resource-ids only — the most stable
    identifier across runs/devices. Falls back to top texts if a screen
    has no resource-ids.
    """
    ids = sorted(
        {
            (e.get("resource-id") or "").split("/")[-1]
            for e in elements
            if e.get("resource-id")
        }
        - {""}
    )
    if not ids:
        ids = sorted(
            {(e.get("text") or "").strip() for e in elements if e.get("text")}
            - {""}
        )[:10]
    blob = "|".join(ids)
    return "unk:" + hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


# ── Public entry point ──────────────────────────────────────────────────


def compute_identity(
    raw_page_source: str,
    signatures: Dict[str, List[Dict[str, Any]]],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> Tuple[Optional[str], str, float, List[str]]:
    """Compute (screen_id, novelty_key, confidence, matched_signature_descriptors).

    - screen_id   matched seeded screen name when confidence >= threshold,
                  else None.
    - novelty_key  screen_id when matched, else a stable unknown-signature
                  hash. Use this as the de-dup key for novelty.
    """
    elements = parse_page_source(raw_page_source)
    if not elements:
        return None, "unk:empty", 0.0, []
    screen, score, matched = match_screen(elements, signatures)
    if screen and score >= threshold:
        return screen, screen, score, matched
    return None, stable_unknown_signature(elements), score, matched
