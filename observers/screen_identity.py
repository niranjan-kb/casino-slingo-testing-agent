"""Screen identity computation for the observer framework.

Reuses the matching logic from tools/casino_qa/detect_screen.py to derive
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
                "clickable": (attrs.get("clickable") == "true"),
                "focusable": (attrs.get("focusable") == "true"),
                "scrollable": (attrs.get("scrollable") == "true"),
            }
        )
    return elements


# ── Spec 005 T043: interactive-element enumeration for the action frontier ─

# Substrings (in resource-id or content-desc) that mark destructive controls.
# Mirrors `_DESTRUCTIVE_VERBS` in shared/screen_graph.py.
_DESTRUCTIVE_SUBSTRINGS = (
    "deposit_submit", "withdraw_submit", "kyc_submit",
    "account_close", "promo_redeem", "fancash_convert",
)
_REVERSIBLE_SUBSTRINGS = (
    "checkbox", "toggle", "switch", "slider",
)


def _classify_side_effect(element: Dict[str, Any]) -> str:
    """Heuristic: idempotent | reversible | destructive.

    Rules:
      - Destructive: resource-id or content-desc matches a known
        destructive substring (deposit_submit etc.).
      - Reversible: control type implies state-toggling (checkboxes,
        switches) — re-tapping reverses the effect.
      - Default: idempotent (covers nav taps, scroll, neutral buttons).
    """
    rid = (element.get("resource-id") or "").lower()
    desc = (element.get("content-desc") or "").lower()
    blob = f"{rid}|{desc}"
    if any(s in blob for s in _DESTRUCTIVE_SUBSTRINGS):
        return "destructive"
    cls = (element.get("class") or "").lower()
    if any(s in blob for s in _REVERSIBLE_SUBSTRINGS) or "toggle" in cls or "switch" in cls:
        return "reversible"
    return "idempotent"


def _stable_element_id(element: Dict[str, Any]) -> Optional[str]:
    """Pick the most stable identifier for an element — for frontier key.

    Preference order:
      1. resource-id (short form, post-`/`)
      2. content-desc
      3. text (only if reasonably short, else skip — text drifts)

    Returns None for elements with no stable handle (will be excluded
    from the frontier; we only track addressable controls).
    """
    rid = element.get("resource-id") or ""
    if rid:
        return rid.split("/")[-1] if "/" in rid else rid
    desc = (element.get("content-desc") or "").strip()
    if desc:
        return desc
    text = (element.get("text") or "").strip()
    if text and len(text) <= 64:
        return text
    return None


def extract_interactive_elements(
    elements: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Filter parsed elements to interactive controls — frontier candidates.

    An element is interactive if it has `clickable=true` or `focusable=true`
    (Android), or its class implies interactivity (Button/EditText/etc.).
    De-duplicates by (element_id) so each addressable control yields one row.
    """
    out: Dict[str, Dict[str, str]] = {}
    for el in elements:
        if not (el.get("clickable") or el.get("focusable")):
            cls = (el.get("class") or "").lower()
            if not any(k in cls for k in (
                "button", "edittext", "imagebutton", "switch", "checkbox",
                "tab", "menuitem",
            )):
                continue
        eid = _stable_element_id(el)
        if not eid:
            continue
        if eid not in out:
            out[eid] = {
                "element_id": eid,
                "side_effect": _classify_side_effect(el),
            }
    return list(out.values())


# ── Spec 005 T046: lobby-walk game-tile extraction ─────────────────────────

# A lobby tile is recognized by these resource-id substrings.
_TILE_ID_SUBSTRINGS = ("game_tile", "lobby_tile", "casino_tile", "tile_card")
# Slug fallback derived from text — strip non-alnum, lowercase, dash-join.
_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Kind inference from tile text or context. Lower-priority than explicit
# attribute on the tile.
_KIND_KEYWORDS = {
    "slingo":     ("slingo",),
    "blackjack":  ("blackjack", "21"),
    "roulette":   ("roulette",),
    "slots":      ("slot", "slots", "spin"),
}


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


def _infer_kind(blob: str) -> Optional[str]:
    blob = blob.lower()
    for kind, keys in _KIND_KEYWORDS.items():
        if any(k in blob for k in keys):
            return kind
    return None


def extract_game_tiles(
    elements: List[Dict[str, Any]],
    *,
    fallback_kind: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Pull (slug, display_name, kind) tuples for each lobby tile.

    Matches tiles by their resource-id substring (`game_tile` etc.). Slug
    comes from the resource-id's last path segment when present, else from
    the slugified display text. Kind is inferred from the tile blob; if the
    blob is silent, falls back to caller-supplied `fallback_kind` (e.g.
    derived from category screen context).

    Returns at most one entry per slug; first occurrence wins.
    """
    out: Dict[str, Dict[str, str]] = {}
    for el in elements:
        rid = (el.get("resource-id") or "").lower()
        if not any(s in rid for s in _TILE_ID_SUBSTRINGS):
            continue
        text = (el.get("text") or "").strip()
        desc = (el.get("content-desc") or "").strip()
        display = text or desc
        if not display:
            continue
        slug_raw = rid.split("/")[-1] if "/" in rid else rid
        slug = slug_raw or _slugify(display)
        if not slug or slug in out:
            continue
        kind = _infer_kind(f"{display} {rid} {desc}") or fallback_kind
        if not kind:
            continue
        out[slug] = {"slug": slug, "display_name": display, "kind": kind}
    return list(out.values())


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
