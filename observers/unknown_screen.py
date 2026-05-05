"""UnknownScreenObserver — fires when the current page-source matches no seeded screen.

This is the truly-novel signal. It replaces an earlier content-hash novelty
observer that fired on every page-source dump (each XML differs by whitespace
and dynamic IDs even for the same screen). Now novelty is keyed on real
screen identity:

  matched seeded screen → no fire (familiar territory)
  no seeded screen      → fire once per unknown signature per run

Useful in the report as "agent encountered something not in the screen-map" —
exactly the post-login loyalty modal class of finding. Once a previously
unknown screen is seeded into screen_signatures, subsequent runs stop firing
for it.

Severity is `info` (it's evidence, not a regression). v1 emits no sub_flow;
the curiosity-driven probe sub_flow lands in a later push.
"""

from __future__ import annotations

from typing import Any, Dict, List

from observers import register
from observers.base import ObservationResult, ScreenContext


class UnknownScreenObserver:
    id = "obs.unknown_screen"
    spec_url: str = None  # type: ignore[assignment]
    severity_on_fail = "info"

    def trigger(self, ctx: ScreenContext) -> bool:
        # Fire only when the screen is unmatched AND first-seen this run.
        return bool(ctx.novelty) and ctx.screen_id is None and bool(
            ctx.screen_signature
        )

    def verify(self, ctx: ScreenContext) -> ObservationResult:
        sig = ctx.screen_signature or ""
        last = ctx.last_tool_name or "?"
        return ObservationResult(
            observer_id=self.id,
            matched=True,
            severity="info",
            summary=(
                f"Unknown screen after {last} — signature {sig[:20]}… "
                "(no seeded screen_signatures matched; consider seeding it)"
            ),
            spec_link=None,
            pass_fail="n/a",
            auto_handle=False,
            screen_signature=sig,
            screen_id=None,
        )

    def sub_flow(self, ctx: ScreenContext) -> List[Dict[str, Any]]:
        # Probe sub_flow (curiosity-driven exploration of unknown screens)
        # deferred to a later push.
        return []


register(UnknownScreenObserver())
