"""
Scale Vision Review Agent.  [SHELVED — 2026-08-04]

SHELVED in favour of a better path. The existing scale validator is a *calibrated*
Gemini GCP service, and per Clayton (ctsims) Gemini outperforms Claude on this
vision task and is cheaper — so the plan is to EXTEND that Gemini service with
analog-dial-reading instructions rather than run this separate Claude agent. This
file is kept for reference only; it is intentionally NOT registered (see the
commented-out @register below), so it will not appear in the AI-agent list.
To revive it: uncomment @register and provision ANTHROPIC_API_KEY in the env.

Reads a weight-scale photo with a multimodal LLM (Claude vision) and checks
whether it matches the FLW's typed weight.

Unlike the `scale_validation` gateway agent (which is built for DIGITAL LCD
scales and returns near-100% "no-match" on analog dials), this agent handles
ANALOG DIAL scales — the UNICEF Salter (EHA/BERI) and KINLee (NAMA) dials —
as well as digital ones. Validated manually: Claude vision reads those dials
(e.g. a Salter needle just past "2" → ~2.2 kg, matching a typed 2200 g).

Plugs into the same audit pipeline as scale_validation: it receives raw image
bytes in context.images["scale"] and the typed value in form_data["reading"].

Requires ANTHROPIC_API_KEY in the process environment (pydantic-ai reads the
provider key from the OS env, not Django settings). The audit review runs in
the Celery worker, so the key must be present on that service.

Optional Django settings (all have sensible defaults):
  SCALE_VISION_MODEL         pydantic-ai model id (default claude-sonnet-4-5)
  SCALE_VISION_TOLERANCE_G   grams tolerance for a "match" (default 200)
  SCALE_VISION_TOLERANCE_PCT fractional tolerance (default 0.10)
"""

import asyncio
import logging

from pydantic import BaseModel, Field

from commcare_connect.labs.ai_review_agents.base import BaseAIReviewAgent
from commcare_connect.labs.ai_review_agents.registry import register  # noqa: F401  (used when revived; see docstring)
from commcare_connect.labs.ai_review_agents.types import ReviewContext, ReviewResult

logger = logging.getLogger(__name__)


class _ScaleReading(BaseModel):
    """Structured output the vision model must return."""

    reading_value_grams: float | None = Field(
        default=None,
        description="The weight you read from the scale, in grams (e.g. 2200). null if you cannot read it.",
    )
    unreadable: bool = Field(
        default=False,
        description="True if the photo is too blurry, dark, cropped, or obscured to read the scale reliably.",
    )
    matches: bool = Field(
        default=False,
        description="True if the scale reading is consistent with the typed weight within normal tolerance.",
    )
    confidence: float = Field(default=0.0, description="Your confidence in the reading, 0.0 to 1.0.")
    notes: str = Field(default="", description="Brief note on what the dial/display showed.")


# @register  # SHELVED: intentionally NOT registered (see module docstring). Uncomment to revive.
class ScaleVisionAgent(BaseAIReviewAgent):
    """AI review agent that reads a scale photo (analog or digital) with a vision LLM."""

    agent_id = "scale_vision"
    name = "Scale Vision (analog + digital)"
    description = (
        "Reads the weight from a scale photo with a vision AI and compares it to the typed value. "
        "Handles analog dial scales (UNICEF Salter, KINLee), not just digital displays."
    )
    result_actions = {
        "pass_matched": {
            "ai_result": "match",
            "human_result": "pass",
            "button_label": "Pass all Matched",
        },
        "fail_unmatched": {
            "ai_result": "no_match",
            "human_result": "fail",
            "button_label": "Fail all Unmatched",
        },
    }

    DEFAULT_MODEL = "anthropic:claude-sonnet-4-5-20250929"

    @property
    def model(self) -> str:
        return self.get_config("SCALE_VISION_MODEL", self.DEFAULT_MODEL)

    @property
    def tolerance_g(self) -> float:
        return float(self.get_config("SCALE_VISION_TOLERANCE_G", 200))

    @property
    def tolerance_pct(self) -> float:
        return float(self.get_config("SCALE_VISION_TOLERANCE_PCT", 0.10))

    def validate_context(self, context: ReviewContext) -> list[str]:
        errors = []
        if "scale" not in context.images and not context.images:
            errors.append("Missing scale image (images['scale'] or any image)")
        if context.get_field("reading") in (None, ""):
            errors.append("Missing weight reading (form_data['reading'])")
        return errors

    def _prompt(self, reading: str) -> str:
        return (
            "You are auditing a child's weight measurement in a Kangaroo Mother Care program. "
            f"A frontline health worker typed a weight of {reading} grams for this visit. "
            "The attached photo shows the weighing scale used. It may be an ANALOG DIAL scale "
            "(a round UNICEF Salter face marked in kilograms, where each large number is a kg and "
            "the small ticks are about 100 g, read by where the needle points) or a DIGITAL LCD.\n\n"
            "Read the weight actually shown on the scale as carefully as you can, and convert it to grams. "
            "For an analog dial, reason about the needle position relative to the numbered kg marks.\n\n"
            f"Then decide whether the scale reading is CONSISTENT with the typed {reading} g, allowing for "
            "normal analog reading tolerance (roughly +/- 200 g). "
            "If the photo is too blurry, dark, cropped, or obstructed to read the scale reliably, "
            "set unreadable=true and do not guess. "
            "Return the grams you read, whether it matches, your confidence, and a short note."
        )

    def review(self, context: ReviewContext) -> ReviewResult:
        validation_errors = self.validate_context(context)
        if validation_errors:
            return ReviewResult.error("; ".join(validation_errors))

        image_bytes = context.get_image("scale")
        if image_bytes is None and context.images:
            image_bytes = next(iter(context.images.values()))
        if not image_bytes:
            return ReviewResult.error("No image bytes available")

        reading = str(context.get_field("reading", ""))

        try:
            from pydantic_ai import Agent
            from pydantic_ai.messages import BinaryContent

            media_type = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            agent = Agent(self.model, output_type=_ScaleReading)

            async def _run():
                result = await agent.run(
                    [self._prompt(reading), BinaryContent(data=image_bytes, media_type=media_type)]
                )
                return result.output

            out = asyncio.run(_run())
        except Exception as e:
            self.logger.warning(f"[scale_vision] vision call failed: {e}")
            return ReviewResult.error(f"vision error: {repr(e)[:150]}")

        details = {
            "read_grams": out.reading_value_grams,
            "confidence": out.confidence,
            "notes": out.notes,
            "model": self.model,
        }

        # An unreadable photo must NOT be scored as a fail — surface it for a human.
        if out.unreadable:
            return ReviewResult.skipped("scale unreadable in photo", **details)

        # Trust the model's match verdict, but re-derive numerically when it read a value,
        # so the match tolerance is explicit and consistent.
        matched = bool(out.matches)
        if out.reading_value_grams is not None:
            try:
                typed = float(reading)
                tol = max(self.tolerance_g, self.tolerance_pct * typed)
                matched = abs(float(out.reading_value_grams) - typed) <= tol
            except (TypeError, ValueError):
                pass

        if matched:
            return ReviewResult.success(confidence=out.confidence, match=True, **details)
        return ReviewResult.failure(confidence=out.confidence, match=False, **details)
