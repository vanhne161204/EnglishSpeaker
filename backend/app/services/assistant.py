"""AI conversation-help service — the in-room coach (PRD §8.8).

Powered by the Claude API when ``ANTHROPIC_API_KEY`` is set (Haiku — the in-call
tier from docs/06_Architecture.md). Falls back to a clearly-labelled stub so the
demo runs with zero configuration and never crashes a live call. The coach is
deliberately short and gentle (PRD §8.8 suggestion rules) to lower the fear of
making mistakes.
"""

import logging

from app.core.config import settings
from app.models.doc import DocSection
from app.models.enums import DocSectionType
from app.repositories.doc import DocRepository
from app.schemas.assist import AssistKind, AssistRequest, AssistResult

logger = logging.getLogger(__name__)

# Cap how much trusted material we inject so the prompt stays small and cheap.
_MAX_SECTIONS = 6
_MAX_SECTION_CHARS = 400
# Only the first few children of a section — enough to steer the model, not a dump.
_MAX_CHILDREN = 8

_SYSTEM_PROMPTS: dict[AssistKind, str] = {
    AssistKind.improve: (
        "You are a kind English-speaking coach in a language-practice app. "
        "Rewrite the user's sentence so it sounds natural and correct, keeping "
        "their meaning and a similar length. Be encouraging, never critical. "
        "Reply with ONLY the improved sentence — no quotes, labels, or notes."
    ),
    AssistKind.reply: (
        "You are a kind English-speaking coach in a language-practice app. "
        "Suggest one short, natural thing the learner could say next in the "
        "conversation. Keep it simple and friendly. Reply with ONLY the "
        "suggested sentence — no quotes, labels, or notes."
    ),
}


class AssistantService:
    def __init__(self, docs: DocRepository | None = None) -> None:
        # Optional so the service still works without DB access (e.g. unit tests).
        self.docs = docs

    async def assist(self, payload: AssistRequest) -> AssistResult:
        # Ground the coach in the topic's trusted documentation when available (RAG).
        trusted = await self._topic_context(payload)
        if settings.anthropic_api_key:
            try:
                return await self._with_claude(payload, trusted)
            except Exception as exc:  # noqa: BLE001 — never fail the call; degrade to stub
                logger.warning("Claude assist failed, falling back to stub: %s", exc)

        return self._stub(payload)

    async def _topic_context(self, payload: AssistRequest) -> str:
        """Flatten the topic's doc into a few short prompt lines (PRD §8.2)."""
        if payload.topic_id is None or self.docs is None:
            return ""
        doc = await self.docs.get_by_topic(payload.topic_id)
        if doc is None:
            return ""
        lines = [
            line
            for section in doc.sections[:_MAX_SECTIONS]
            if (line := _section_line(section))
        ]
        if not lines:
            return ""
        return "Use this trusted material about the topic when helpful:\n" + "\n".join(lines)

    async def _with_claude(self, payload: AssistRequest, trusted: str) -> AssistResult:
        # Imported lazily so the demo runs without the SDK installed.
        from anthropic import AsyncAnthropic

        if payload.kind is AssistKind.improve:
            user_content = payload.text.strip()
        else:
            context = (payload.context or "").strip()
            user_content = (
                f"The other person just said: {context}\nSuggest my reply."
                if context
                else "Suggest a friendly way to start the conversation."
            )

        system = _SYSTEM_PROMPTS[payload.kind]
        if trusted:
            system = f"{system}\n\n{trusted}"

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.assist_model,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        suggestion = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()
        return AssistResult(suggestion=suggestion, kind=payload.kind, provider="claude")

    def _stub(self, payload: AssistRequest) -> AssistResult:
        if payload.kind is AssistKind.improve:
            suggestion = _simple_polish(payload.text.strip())
        else:
            suggestion = "That's interesting! Could you tell me more about it?"
        return AssistResult(suggestion=suggestion, kind=payload.kind, provider="stub")


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
