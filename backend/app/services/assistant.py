"""AI conversation-help service — the in-room coach (PRD §8.8, §10.2).

Owns *what to ask*, never *whom to ask*. Model choice, fallback order, timeouts,
cost recording and spend caps all live behind the ``LLMProvider`` port
(docs/18_AI_Provider_Architecture.md), so switching from GPT to Claude — or
running different models for free and premium learners — is configuration.

Two consequences worth knowing:

* There is no vendor SDK import here and no API-key check. Injecting a
  ``FakeProvider`` makes this service fully testable with no key and no network.
* Every failure path still ends in a clearly-labelled stub. A live room must
  never break because an AI vendor is down.
"""

from __future__ import annotations

import logging

from app.ai.errors import ProviderError
from app.ai.metering import BudgetExceeded
from app.ai.ports import LLMProvider, LLMRequest
from app.ai.routing import Route
from app.models.doc import DocSection
from app.models.enums import DocSectionType
from app.repositories.doc import DocRepository
from app.schemas.assist import AssistKind, AssistRequest, AssistResult
from app.services.prompts import rescue_system, rescue_user

logger = logging.getLogger(__name__)

# Cap how much trusted material we inject so the prompt stays small and cheap.
_MAX_SECTIONS = 6
_MAX_SECTION_CHARS = 400
# Only the first few children of a section — enough to steer the model, not a dump.
_MAX_CHILDREN = 8


class AssistantService:
    def __init__(
        self,
        llm: LLMProvider,
        route: Route,
        docs: DocRepository | None = None,
    ) -> None:
        self._llm = llm
        # The route carries this task's token budget, timeout and effort. They
        # are policy (app/ai/routing.py), not something a service should invent.
        self._route = route
        # Optional so the service still works without DB access (e.g. unit tests).
        self.docs = docs

    async def assist(self, payload: AssistRequest) -> AssistResult:
        # Ground the coach in the topic's trusted documentation when available (RAG).
        trusted = await self._topic_context(payload)

        request = LLMRequest(
            system=rescue_system(payload.kind, payload.level, trusted),
            user=rescue_user(payload.kind, payload.text, payload.context or ""),
            max_tokens=self._route.max_tokens,
            timeout_s=self._route.timeout_s,
            effort=self._route.effort,
            cache_system=self._route.cache_system,
        )

        try:
            response = await self._llm.generate(request)
        except BudgetExceeded as exc:
            # A cap is a normal outcome, not an error — tell the learner plainly.
            return AssistResult(
                suggestion=exc.detail, kind=payload.kind, provider="limit", degraded=True
            )
        except ProviderError as exc:
            logger.warning("AI assist failed, falling back to stub: %s", exc)
            return self._stub(payload)

        text = response.text.strip()
        if not text:
            # A provider that answers with nothing is no better than one that is
            # down. Never hand the learner an empty suggestion box.
            logger.warning("AI assist returned empty text from %s", response.model)
            return self._stub(payload)

        return AssistResult(
            suggestion=text,
            kind=payload.kind,
            provider=response.provider,
            degraded=response.degraded,
        )

    async def _topic_context(self, payload: AssistRequest) -> str:
        """Flatten the topic's doc into a few short prompt lines (PRD §8.2)."""
        if payload.topic_id is None or self.docs is None:
            return ""
        doc = await self.docs.get_by_topic(payload.topic_id)
        if doc is None:
            return ""
        lines = [
            line for section in doc.sections[:_MAX_SECTIONS] if (line := _section_line(section))
        ]
        if not lines:
            return ""
        return "Use this trusted material about the topic when helpful:\n" + "\n".join(lines)

    def _stub(self, payload: AssistRequest) -> AssistResult:
        if payload.kind is AssistKind.improve:
            suggestion = _simple_polish(payload.text.strip())
        elif payload.kind is AssistKind.ask:
            suggestion = "What do you usually do at the weekend?"
        elif payload.kind is AssistKind.say_this:
            suggestion = _simple_polish(payload.text.strip())
        else:
            suggestion = "That's interesting! Could you tell me more about it?"
        return AssistResult(
            suggestion=suggestion, kind=payload.kind, provider="stub", degraded=True
        )


def _section_line(section: DocSection) -> str:
    """Render one doc section as a single short prompt line, or "" if it's empty."""
    kind = DocSectionType(section.type)
    label = section.title or kind.value

    if kind.holds_items:
        content = ", ".join(item.term for item in section.items[:_MAX_CHILDREN])
    elif kind.holds_questions:
        content = " ".join(q.text for q in section.questions[:_MAX_CHILDREN])
    else:
        content = (section.body or "").replace("\n", " ")

    content = content.strip()[:_MAX_SECTION_CHARS]
    return f"- {label}: {content}" if content else ""


def _simple_polish(text: str) -> str:
    """A tiny deterministic clean-up used by the demo stub (capitalise + end stop)."""
    if not text:
        return text
    polished = text[0].upper() + text[1:]
    if polished[-1] not in ".!?":
        polished += "."
    return polished
