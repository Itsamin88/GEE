"""Optional semantic extraction layer.

The LLM never becomes the source (brief §65). It may only read text this
program has already retrieved and stored, and every field it proposes must
carry an exact supporting passage which is then verified, character for
character, against that stored text. A proposal whose passage does not verify
is discarded and logged.

With no API key the pipeline runs deterministically and enlarges the human
review queue instead of failing (brief §78).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..logging_setup import get_logger
from .model import ClaimItem, _squash

log = get_logger("llm")

PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """\
You are a documentary research assistant for an academic study of intentional
sustainable communities. You are given text that has ALREADY been retrieved from
a named source. Your only job is to say what this text states about a fixed list
of research fields.

ABSOLUTE RULES
1. Never invent a value. If the text does not state it, omit the field.
2. Every value you return must be supported by a passage QUOTED EXACTLY from the
   text given to you, character for character. Do not paraphrase the passage.
3. Never infer from a similar community, from typical values, or from your own
   knowledge of this community. Only this text counts.
4. Distinguish "the text says no" from "the text says nothing". Only return
   `explicitly absent` for a practice when the text contains an actual denial.
5. A photograph or an image caption never evidences a practice on its own. Only
   a statement of the practice does.
6. Never return a value for polygon area, elevation, rainfall, slope, biome,
   climate class, vegetation indices or any other satellite-derived quantity.
7. Record the year a figure REFERS TO separately from the year it was published.
8. Do not convert or round. Give the value as the text states it.

Return ONLY a JSON object of this shape:
{"claims": [{"field": "<field name>", "value": "<value>",
             "passage": "<exact quote from the text>",
             "reference_year": <year or null>,
             "confidence": <0.0-1.0>,
             "reasoning": "<one short sentence>"}]}
If the text supports nothing, return {"claims": []}.
"""


@dataclass
class LlmProposal:
    field_name: str
    value: str
    passage: str
    reference_year: int | None
    confidence: float
    reasoning: str
    verified: bool = False
    rejection: str = ""


@dataclass
class LlmOutcome:
    available: bool
    proposals: list[LlmProposal] = field(default_factory=list)
    rejected: list[LlmProposal] = field(default_factory=list)
    calls: int = 0
    detail: str = ""
    model: str = ""


class SemanticExtractor:
    """A thin, strictly-bounded wrapper over the Claude API."""

    def __init__(self, *, api_key: str | None, model: str, config: Mapping[str, Any],
                 allowed_fields: Iterable[str], forbidden_fields: Iterable[str]):
        self.model = model
        self.max_chars = int(config.get("max_chars_per_call", 24000))
        self.max_calls = int(config.get("max_calls_per_community", 120))
        self.temperature = float(config.get("temperature", 0))
        self.require_verbatim = bool(config.get("require_verbatim_passage", True))
        self.allowed = {str(f) for f in allowed_fields}
        self.forbidden = {str(f).lower() for f in forbidden_fields}
        self.calls = 0
        self.client: Any = None
        self.unavailable_reason = ""
        if not api_key:
            self.unavailable_reason = "no ANTHROPIC_API_KEY"
            return
        try:
            import anthropic  # type: ignore

            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            self.unavailable_reason = "the anthropic package is not installed"
        except Exception as exc:  # pragma: no cover
            self.unavailable_reason = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return self.client is not None

    def extract(self, text: str, *, fields: Sequence[str], context: Mapping[str, Any]) -> LlmOutcome:
        """Ask for structured claims, then verify every passage against the text."""
        if not self.available:
            return LlmOutcome(available=False, detail=self.unavailable_reason)
        if self.calls >= self.max_calls:
            return LlmOutcome(available=False,
                              detail=f"per-community call budget of {self.max_calls} is spent")
        excerpt = text[: self.max_chars]
        prompt = (
            f"SOURCE: {context.get('source_id', 'unknown')} "
            f"({context.get('source_class', 'unknown class')})\n"
            f"TITLE: {context.get('title', '')}\n"
            f"PUBLICATION DATE: {context.get('publication_date') or 'not stated'}\n\n"
            f"FIELDS TO CONSIDER:\n" + "\n".join(f"- {f}" for f in fields) + "\n\n"
            f"TEXT:\n<<<\n{excerpt}\n>>>\n"
        )
        try:
            self.calls += 1
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=self.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            body = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
        except Exception as exc:
            log.warning("[LLM] call failed: %s", exc)
            return LlmOutcome(available=True, calls=self.calls,
                              detail=f"{type(exc).__name__}: {exc}", model=self.model)

        outcome = LlmOutcome(available=True, calls=self.calls, model=self.model)
        for proposal in self._parse(body):
            reason = self._reject_reason(proposal, excerpt)
            if reason:
                proposal.rejection = reason
                outcome.rejected.append(proposal)
                log.info("[LLM] proposal discarded (%s): %s = %r",
                         reason, proposal.field_name, proposal.value[:60])
            else:
                proposal.verified = True
                outcome.proposals.append(proposal)
        return outcome

    def _reject_reason(self, proposal: LlmProposal, text: str) -> str:
        if proposal.field_name.lower() in self.forbidden:
            return "satellite-only or researcher-owned field"
        if proposal.field_name not in self.allowed:
            return "field is not in the canonical schema"
        if not proposal.value.strip():
            return "empty value"
        if self.require_verbatim:
            if not proposal.passage.strip():
                return "no supporting passage given"
            if _squash(proposal.passage) not in _squash(text):
                return "supporting passage does not occur in the stored text"
        return ""

    @staticmethod
    def _parse(body: str) -> list[LlmProposal]:
        match = re.search(r"\{.*\}", body, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group())
        except json.JSONDecodeError:
            return []
        proposals: list[LlmProposal] = []
        for item in payload.get("claims", []) or []:
            if not isinstance(item, dict):
                continue
            field_name = str(item.get("field", "")).strip()
            value = str(item.get("value", "")).strip()
            if not field_name or not value:
                continue
            year = item.get("reference_year")
            try:
                year_value = int(year) if year not in (None, "", "null") else None
            except (TypeError, ValueError):
                year_value = None
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            proposals.append(
                LlmProposal(
                    field_name=field_name,
                    value=value,
                    passage=str(item.get("passage", "")),
                    reference_year=year_value,
                    confidence=max(0.0, min(1.0, confidence)),
                    reasoning=str(item.get("reasoning", ""))[:500],
                )
            )
        return proposals


def to_claims(outcome: LlmOutcome) -> list[ClaimItem]:
    """Convert verified proposals into claims, stamped with the model identity."""
    claims: list[ClaimItem] = []
    for proposal in outcome.proposals:
        claims.append(
            ClaimItem(
                field_name=proposal.field_name,
                value=proposal.value,
                value_type="text",
                original_value=proposal.value,
                exact_wording=proposal.passage[:2000],
                reference_year=proposal.reference_year,
                confidence=proposal.confidence,
                rationale=proposal.reasoning,
                extractor=f"llm:{outcome.model}",
                model_name=outcome.model,
                prompt_version=PROMPT_VERSION,
                verified_passage=True,
                notes="passage verified against the stored text before acceptance",
            )
        )
    return claims
