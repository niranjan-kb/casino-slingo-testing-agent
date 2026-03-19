"""
Perception activities for the self-improving agent.

These Temporal activities handle:
1. Screen detection (element-based primary, vision fallback)
2. Element location (DB lookup → vision fallback)
3. Tap verification and coordinate correction
4. Coordinate lookup from the screen map DB

All activities interact with the ScreenMapDB and optionally call
appium-mcp tools or LLM vision for discovery/correction.
"""

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from litellm import completion
from temporalio import activity

from shared.screen_map_db import ScreenMapDB

# ── Data types for activity I/O ──────────────────────────────────────


@dataclass
class DeviceContext:
    """Identifies the current device for DB lookups."""
    device_name: str  # e.g., "Pixel_5_API_34"
    resolution: str   # e.g., "1080x1920"
    platform: str = "android"


@dataclass
class DetectScreenInput:
    """Input for screen detection."""
    device: DeviceContext
    found_elements: List[Dict[str, Any]]  # results from appium_find_element
    screenshot_path: Optional[str] = None  # for vision fallback
    app_context: str = "platform"


@dataclass
class DetectScreenResult:
    """Result of screen detection."""
    screen_name: str         # detected screen name
    confidence: float        # 0.0 to 1.0
    method: str              # 'element', 'vision', 'unknown'
    matched_signatures: List[str] = field(default_factory=list)
    raw_vision_response: Optional[str] = None


@dataclass
class LookupCoordsInput:
    """Input for coordinate lookup."""
    device: DeviceContext
    app_context: str
    screen_name: str
    element_name: str


@dataclass
class LookupCoordsResult:
    """Result of coordinate lookup."""
    found: bool
    x: Optional[int] = None
    y: Optional[int] = None
    confidence: float = 0.0
    source: str = "none"       # 'db', 'cross_device', 'vision', 'none'
    needs_verification: bool = True


@dataclass
class VerifyTapInput:
    """Input for tap verification."""
    device: DeviceContext
    app_context: str
    screen_name: str
    element_name: str
    tapped_x: int
    tapped_y: int
    expected_screen_after: Optional[str] = None  # what screen we expect to be on after tap
    screenshot_path: Optional[str] = None        # screenshot taken after the tap
    found_elements_after: Optional[List[Dict[str, Any]]] = None  # elements found after tap


@dataclass
class VerifyTapResult:
    """Result of tap verification."""
    success: bool
    current_screen: Optional[str] = None
    correction: Optional[Dict[str, int]] = None  # {"x": new_x, "y": new_y} if corrected
    observation_id: Optional[int] = None


@dataclass
class LocateElementInput:
    """Input for vision-based element location."""
    device: DeviceContext
    app_context: str
    screen_name: str
    element_name: str
    element_description: str   # human-readable description for the LLM
    screenshot_path: str


@dataclass
class LocateElementResult:
    """Result of vision-based element location."""
    found: bool
    x: Optional[int] = None
    y: Optional[int] = None
    confidence: float = 0.0
    raw_response: Optional[str] = None


# ── Activity implementations ─────────────────────────────────────────


class PerceptionActivities:
    """Temporal activities for screen perception and coordinate management."""

    def __init__(self, db: ScreenMapDB):
        self.db = db
        self.llm_model = os.environ.get("LLM_MODEL", "openai/gpt-4")
        self.llm_key = os.environ.get("LLM_KEY")
        self.llm_base_url = os.environ.get("LLM_BASE_URL")
        # Vision model — prefer a vision-capable model, fall back to main model
        self.vision_model = os.environ.get("VISION_MODEL", self.llm_model)

    def _get_device_profile_id(self, device: DeviceContext) -> str:
        """Ensure device profile exists and return its ID."""
        return self.db.ensure_device_profile(
            device.device_name, device.resolution, device.platform,
        )

    # ── Screen Detection ─────────────────────────────────────────

    @activity.defn
    async def detect_screen(self, input: DetectScreenInput) -> DetectScreenResult:
        """Detect which screen the app is currently showing.

        Primary: match found_elements against screen signatures in DB.
        Fallback: LLM vision on screenshot (if provided and element match fails).
        """
        profile_id = self._get_device_profile_id(input.device)
        signatures = self.db.get_screen_signatures(input.app_context)

        # Phase 1: Element-based detection
        result = self._match_signatures(input.found_elements, signatures)
        if result:
            activity.logger.info(f"Screen detected via elements: {result.screen_name}")
            # Also capture any element coordinates we found
            self._cache_found_elements(profile_id, input.app_context, result.screen_name, input.found_elements)
            return result

        # Phase 2: Vision-based fallback
        if input.screenshot_path:
            activity.logger.info("Element detection inconclusive, falling back to vision")
            result = await self._detect_screen_via_vision(
                input.screenshot_path, list(signatures.keys()), input.app_context,
            )
            if result:
                return result

        # Unknown screen
        return DetectScreenResult(
            screen_name="unknown",
            confidence=0.0,
            method="unknown",
        )

    def _match_signatures(
        self,
        found_elements: List[Dict[str, Any]],
        signatures: Dict[str, List[Dict[str, Any]]],
    ) -> Optional[DetectScreenResult]:
        """Match found elements against screen signatures. Returns best match."""
        if not found_elements:
            return None

        # Build lookup sets from found elements
        found_texts = set()
        found_ids = set()
        found_classes = set()
        for elem in found_elements:
            if text := elem.get("text"):
                found_texts.add(text)
                # Also check partial matches (element text might be longer)
                for t in found_texts.copy():
                    found_texts.add(t.strip())
            if elem_id := elem.get("resource-id", elem.get("id", "")):
                # Extract just the ID part after the last /
                short_id = elem_id.split("/")[-1] if "/" in elem_id else elem_id
                found_ids.add(short_id)
                found_ids.add(elem_id)
            if cls := elem.get("class", elem.get("className")):
                found_classes.add(cls)

        # Score each screen
        scores: Dict[str, tuple] = {}  # screen_name -> (score, matched_sigs)
        for screen_name, sigs in signatures.items():
            score = 0
            matched = []
            for sig in sigs:
                sig_type = sig["signature_type"]
                sig_value = sig["signature_value"]
                hit = False

                if sig_type == "element_text":
                    # Check if any found text contains the signature value
                    hit = any(sig_value.lower() in t.lower() for t in found_texts)
                elif sig_type == "element_id":
                    hit = any(sig_value.lower() in i.lower() for i in found_ids)
                elif sig_type == "element_class":
                    hit = sig_value in found_classes

                if hit:
                    score += sig["priority"]
                    matched.append(f"{sig_type}:{sig_value}")

            if score > 0:
                scores[screen_name] = (score, matched)

        if not scores:
            return None

        # Return highest scoring screen
        best_screen = max(scores, key=lambda k: scores[k][0])
        best_score, best_matched = scores[best_screen]
        max_possible = sum(s["priority"] for s in signatures.get(best_screen, []))
        confidence = min(best_score / max(max_possible, 1), 1.0)

        return DetectScreenResult(
            screen_name=best_screen,
            confidence=confidence,
            method="element",
            matched_signatures=best_matched,
        )

    def _cache_found_elements(
        self,
        profile_id: str,
        app_context: str,
        screen_name: str,
        found_elements: List[Dict[str, Any]],
    ) -> None:
        """Cache element coordinates discovered via appium_find_element."""
        for elem in found_elements:
            # Only cache elements with both coordinates and a usable name
            bounds = elem.get("bounds")
            x = elem.get("x")
            y = elem.get("y")
            if bounds and not (x and y):
                # Parse bounds string like "[100,200][300,400]" to center coords
                try:
                    parts = bounds.replace("][", ",").strip("[]").split(",")
                    if len(parts) == 4:
                        x = (int(parts[0]) + int(parts[2])) // 2
                        y = (int(parts[1]) + int(parts[3])) // 2
                except (ValueError, IndexError):
                    continue

            if x is None or y is None:
                continue

            # Determine element name from text, id, or content-desc
            elem_name = None
            if text := elem.get("text"):
                elem_name = text.lower().replace(" ", "_")[:30]
            elif res_id := elem.get("resource-id", elem.get("id", "")):
                elem_name = res_id.split("/")[-1] if "/" in res_id else res_id
            elif desc := elem.get("content-desc", elem.get("contentDescription")):
                elem_name = desc.lower().replace(" ", "_")[:30]

            if elem_name:
                self.db.upsert_element(
                    device_profile_id=profile_id,
                    app_context=app_context,
                    screen_name=screen_name,
                    element_name=elem_name,
                    x=int(x),
                    y=int(y),
                    source="element",
                    confidence=0.8,  # high confidence — came from actual element detection
                )

    async def _detect_screen_via_vision(
        self,
        screenshot_path: str,
        known_screens: List[str],
        app_context: str,
    ) -> Optional[DetectScreenResult]:
        """Use LLM vision to detect which screen is shown."""
        try:
            image_data = _load_image_as_base64(screenshot_path)
            if not image_data:
                return None

            screen_list = ", ".join(known_screens + ["unknown"])
            prompt = (
                f"Look at this mobile app screenshot. Which screen is this?\n"
                f"Choose exactly ONE from: [{screen_list}]\n\n"
                f"Respond with ONLY a JSON object:\n"
                f'{{"screen": "<screen_name>", "confidence": <0.0-1.0>}}'
            )

            response = await self._call_vision(prompt, image_data)
            data = json.loads(response)
            screen = data.get("screen", "unknown")
            conf = float(data.get("confidence", 0.5))

            return DetectScreenResult(
                screen_name=screen,
                confidence=conf,
                method="vision",
                raw_vision_response=response,
            )
        except Exception as e:
            activity.logger.error(f"Vision screen detection failed: {e}")
            return None

    # ── Coordinate Lookup ────────────────────────────────────────

    @activity.defn
    async def lookup_coords(self, input: LookupCoordsInput) -> LookupCoordsResult:
        """Look up element coordinates from DB with cross-device fallback."""
        profile_id = self._get_device_profile_id(input.device)

        # Try exact device match first
        elem = self.db.get_element_coords(
            profile_id, input.app_context, input.screen_name, input.element_name,
        )
        if elem:
            needs_verify = self.db.should_verify_tap(
                profile_id, input.app_context, input.screen_name, input.element_name,
            )
            return LookupCoordsResult(
                found=True,
                x=elem["x"],
                y=elem["y"],
                confidence=elem["confidence"],
                source="db",
                needs_verification=needs_verify,
            )

        # Try cross-device fallback
        guess = self.db.get_best_guess_coords(
            input.app_context, input.screen_name, input.element_name, input.device.resolution,
        )
        if guess:
            # Cache the cross-device guess for this device
            self.db.upsert_element(
                profile_id, input.app_context, input.screen_name, input.element_name,
                guess["x"], guess["y"],
                source="cross_device",
                element_type=guess.get("element_type"),
                intent=guess.get("intent"),
                confidence=0.3,  # low confidence — untested on this device
            )
            return LookupCoordsResult(
                found=True,
                x=guess["x"],
                y=guess["y"],
                confidence=0.3,
                source="cross_device",
                needs_verification=True,
            )

        return LookupCoordsResult(found=False)

    # ── Vision Element Location ──────────────────────────────────

    @activity.defn
    async def locate_element_vision(self, input: LocateElementInput) -> LocateElementResult:
        """Use LLM vision to find an element's pixel coordinates in a screenshot."""
        profile_id = self._get_device_profile_id(input.device)

        image_data = _load_image_as_base64(input.screenshot_path)
        if not image_data:
            return LocateElementResult(found=False, raw_response="Could not load screenshot")

        prompt = (
            f"Look at this mobile app screenshot ({input.device.resolution} pixels).\n"
            f"Find this UI element: {input.element_description}\n"
            f"The element is on the '{input.screen_name}' screen.\n\n"
            f"Return the CENTER pixel coordinates of this element.\n"
            f"Respond with ONLY a JSON object:\n"
            f'{{"found": true, "x": <pixel_x>, "y": <pixel_y>, "confidence": <0.0-1.0>}}\n'
            f'Or if not visible: {{"found": false}}'
        )

        try:
            response = await self._call_vision(prompt, image_data)
            data = json.loads(response)

            if data.get("found"):
                x, y = int(data["x"]), int(data["y"])
                conf = float(data.get("confidence", 0.7))

                # Cache in DB
                self.db.upsert_element(
                    profile_id, input.app_context, input.screen_name, input.element_name,
                    x, y, source="vision", confidence=conf,
                )

                return LocateElementResult(found=True, x=x, y=y, confidence=conf, raw_response=response)

            return LocateElementResult(found=False, raw_response=response)

        except Exception as e:
            activity.logger.error(f"Vision element location failed: {e}")
            return LocateElementResult(found=False, raw_response=str(e))

    # ── Verify & Correct ─────────────────────────────────────────

    @activity.defn
    async def verify_tap(self, input: VerifyTapInput) -> VerifyTapResult:
        """Verify a tap succeeded and correct coordinates if it didn't.

        Checks if the screen transitioned as expected after a tap.
        If not, logs an observation and optionally uses vision to find
        the correct element location.
        """
        profile_id = self._get_device_profile_id(input.device)

        # Detect current screen after the tap
        detect_input = DetectScreenInput(
            device=input.device,
            found_elements=input.found_elements_after or [],
            screenshot_path=input.screenshot_path,
            app_context=input.app_context,
        )
        current = await self.detect_screen(detect_input)

        # Determine success
        if input.expected_screen_after:
            success = current.screen_name == input.expected_screen_after
        else:
            # No expected screen — just check we're not on the same screen
            # (tap should have caused some transition)
            success = current.screen_name != input.screen_name

        # Record result in DB
        self.db.record_tap_result(
            profile_id, input.app_context, input.screen_name, input.element_name, success,
        )

        correction = None
        if not success and input.screenshot_path:
            # Log the failure observation
            obs_id = self.db.log_observation(
                device_profile_id=profile_id,
                screen_name=input.screen_name,
                element_name=input.element_name,
                action="tap",
                expected_result=f"transition to {input.expected_screen_after or 'next screen'}",
                actual_result=f"still on {current.screen_name}",
                screenshot_path=input.screenshot_path,
            )

            activity.logger.warning(
                f"Tap verification failed: tapped {input.element_name} at "
                f"({input.tapped_x},{input.tapped_y}), expected {input.expected_screen_after}, "
                f"got {current.screen_name}"
            )

            return VerifyTapResult(
                success=False,
                current_screen=current.screen_name,
                observation_id=obs_id,
            )

        if success:
            activity.logger.info(
                f"Tap verified: {input.element_name} → {current.screen_name}"
            )

        return VerifyTapResult(
            success=success,
            current_screen=current.screen_name,
            correction=correction,
        )

    # ── LLM Vision Helper ────────────────────────────────────────

    async def _call_vision(self, prompt: str, image_base64: str) -> str:
        """Call LLM with a vision prompt and image."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                        },
                    },
                ],
            }
        ]

        kwargs = {
            "model": self.vision_model,
            "messages": messages,
            "max_tokens": 200,
        }
        if self.llm_key:
            kwargs["api_key"] = self.llm_key
        if self.llm_base_url:
            kwargs["base_url"] = self.llm_base_url

        response = completion(**kwargs)
        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        return content


# ── Helpers ──────────────────────────────────────────────────────────


def _load_image_as_base64(path: str) -> Optional[str]:
    """Load an image file and return base64-encoded string."""
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
