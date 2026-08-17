"""Business logic for topic documentation (PRD §8.2).

Guards the two rules the database can't express on its own:

1. A topic has at most one doc.
2. A section only accepts the children its ``type`` allows — vocabulary items go
   in ``vocabulary``/``phrases`` sections, questions go in ``questions`` sections.
"""

import uuid
from collections.abc import Sequence

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.doc import AnswerTemplate, Doc, DocItem, DocSection, Question
from app.models.enums import ContentStatus, DocSectionType
from app.repositories.doc import DocRepository
from app.repositories.topic import TopicRepository
from app.schemas.doc import (
    AnswerTemplateCreate,
    AnswerTemplateUpdate,
    DocCreate,
    DocItemCreate,
    DocItemUpdate,
    DocSectionCreate,
    DocSectionUpdate,
    DocUpdate,
    QAPairRead,
    QASet,
    QuestionCreate,
    QuestionRead,
    QuestionUpdate,
    TopicQuestionRead,
)

# Heading given to the `questions` section the simple editor creates for a topic.
_QUESTIONS_SECTION_TITLE = "Conversation questions"


def _to_qa_pair(question: Question) -> QAPairRead:
    """Flatten a question and its first answer template into one editable pair."""
    first = question.answer_templates[0] if question.answer_templates else None
    return QAPairRead(
        id=question.id,
        text=question.text,
        answer=first.template if first else None,
        sort_order=question.sort_order,
    )


class DocService:
    def __init__(self, docs: DocRepository, topics: TopicRepository) -> None:
        self.docs = docs
        self.topics = topics

    # --- Docs ---------------------------------------------------------------

    async def list_docs(self, topic_id: uuid.UUID | None = None) -> Sequence[Doc]:
        return await self.docs.list(topic_id)

    async def get_doc(self, doc_id: uuid.UUID) -> Doc:
        doc = await self.docs.get(doc_id)
        if doc is None:
            raise NotFoundError("Doc not found")
        return doc

    async def get_doc_for_topic(self, topic_id: uuid.UUID) -> Doc:
        if await self.topics.get(topic_id) is None:
            raise NotFoundError("Topic not found")
        doc = await self.docs.get_by_topic(topic_id)
        if doc is None:
            raise NotFoundError("This topic has no documentation yet")
        return doc

    async def create_doc(self, payload: DocCreate) -> Doc:
        # Validate the link explicitly (SQLite doesn't enforce FKs by default).
        if await self.topics.get(payload.topic_id) is None:
            raise NotFoundError("Topic not found")
        if await self.docs.get_by_topic(payload.topic_id):
            raise ConflictError("This topic already has a doc")
        data = payload.model_dump()
        data["status"] = data["status"].value
        return await self.docs.add(Doc(**data))

    async def update_doc(self, doc_id: uuid.UUID, payload: DocUpdate) -> Doc:
        doc = await self.get_doc(doc_id)
        changes = payload.model_dump(exclude_unset=True)
        # ``status`` is NOT NULL, so an explicit null just means "leave it alone".
        status = changes.pop("status", None)
        if status is not None:
            doc.status = ContentStatus(status).value
        for field, value in changes.items():
            setattr(doc, field, value)
        return doc

    async def delete_doc(self, doc_id: uuid.UUID) -> None:
        doc = await self.get_doc(doc_id)
        await self.docs.delete(doc)

    # --- Sections -----------------------------------------------------------

    async def get_section(self, section_id: uuid.UUID) -> DocSection:
        section = await self.docs.get_section(section_id)
        if section is None:
            raise NotFoundError("Section not found")
        return section

    async def create_section(self, doc_id: uuid.UUID, payload: DocSectionCreate) -> DocSection:
        await self.get_doc(doc_id)
        data = payload.model_dump()
        data["type"] = data["type"].value
        # A new section starts empty. Assigning the collections marks them loaded,
        # so serializing the response never triggers a lazy load (which would blow
        # up under asyncio with MissingGreenlet).
        section = DocSection(doc_id=doc_id, **data, items=[], questions=[])
        return await self.docs.add_section(section)

    async def update_section(
        self, section_id: uuid.UUID, payload: DocSectionUpdate
    ) -> DocSection:
        section = await self.get_section(section_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(section, field, value)
        return section

    async def delete_section(self, section_id: uuid.UUID) -> None:
        section = await self.get_section(section_id)
        await self.docs.delete_section(section)

    # --- Items (vocabulary / phrases) ---------------------------------------

    async def create_item(self, section_id: uuid.UUID, payload: DocItemCreate) -> DocItem:
        section = await self.get_section(section_id)
        if not DocSectionType(section.type).holds_items:
            raise BadRequestError(
                f"A '{section.type}' section holds no vocabulary items — "
                "use a 'vocabulary' or 'phrases' section."
            )
        return await self.docs.add_item(DocItem(section_id=section_id, **payload.model_dump()))

    async def get_item(self, item_id: uuid.UUID) -> DocItem:
        item = await self.docs.get_item(item_id)
        if item is None:
            raise NotFoundError("Item not found")
        return item

    async def update_item(self, item_id: uuid.UUID, payload: DocItemUpdate) -> DocItem:
        item = await self.get_item(item_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        return item

    async def delete_item(self, item_id: uuid.UUID) -> None:
        await self.docs.delete_item(await self.get_item(item_id))

    # --- Questions ----------------------------------------------------------

    async def list_topic_questions(
        self, topic_id: uuid.UUID | None = None
    ) -> list[TopicQuestionRead]:
        rows = await self.docs.list_published_questions(topic_id)
        return [
            TopicQuestionRead(
                **QuestionRead.model_validate(question).model_dump(),
                topic_id=t_id,
                topic_title=t_title,
            )
            for question, t_id, t_title in rows
        ]

    async def get_question(self, question_id: uuid.UUID) -> Question:
        question = await self.docs.get_question(question_id)
        if question is None:
            raise NotFoundError("Question not found")
        return question

    # --- Simple question-and-answer editing (PRD §8.1) ----------------------

    async def list_qa_pairs(self, topic_id: uuid.UUID) -> list[QAPairRead]:
        """Every question on a topic as a flat question/answer pair.

        Unlike ``list_topic_questions`` this ignores the doc's status, because the
        admin editor must load what is actually stored — including a draft — or
        saving would silently wipe it.
        """
        if await self.topics.get(topic_id) is None:
            raise NotFoundError("Topic not found")
        doc = await self.docs.get_by_topic(topic_id)
        if doc is None:
            return []
        return [
            _to_qa_pair(question)
            for section in doc.sections
            if DocSectionType(section.type).holds_questions
            for question in section.questions
        ]

    async def replace_qa_pairs(self, topic_id: uuid.UUID, payload: QASet) -> list[QAPairRead]:
        """Save a topic's whole question list in one call.

        Creates whatever the tree needs along the way — the doc, and a
        ``questions`` section — so an admin never has to build the scaffolding by
        hand. Saving *replaces* the list: questions that are no longer in
        ``payload`` are deleted, along with their answer templates.
        """
        topic = await self.topics.get(topic_id)
        if topic is None:
            raise NotFoundError("Topic not found")

        doc = await self.docs.get_by_topic(topic_id)
        if doc is None:
            doc = await self.docs.add(
                Doc(topic_id=topic_id, title=topic.title, level=topic.level, sections=[])
            )
        # Questions only reach learners from a published doc, and saving questions
        # is the admin saying "these are ready" — so publish rather than leave a
        # draft that silently shows nothing.
        doc.status = ContentStatus.published.value

        section = next(
            (s for s in doc.sections if DocSectionType(s.type).holds_questions), None
        )
        if section is None:
            section = await self.docs.add_section(
                DocSection(
                    doc_id=doc.id,
                    type=DocSectionType.questions.value,
                    title=_QUESTIONS_SECTION_TITLE,
                    sort_order=len(doc.sections),
                    items=[],
                    questions=[],
                )
            )

        # Clearing the collection orphans the old rows, so the flush deletes them
        # (and cascades to their answer templates) before the new ones go in.
        section.questions.clear()
        await self.docs.flush()

        for order, item in enumerate(payload.items):
            answer = (item.answer or "").strip()
            # Append to the collection rather than setting ``section_id``: that
            # keeps the in-memory list in step with the database, so the response
            # below sees the new rows.
            section.questions.append(
                Question(
                    text=item.text.strip(),
                    sort_order=order,
                    answer_templates=(
                        [AnswerTemplate(template=answer, sort_order=0)] if answer else []
                    ),
                )
            )
        await self.docs.flush()  # assign ids before they're read back

        return [_to_qa_pair(question) for question in section.questions]

    async def create_question(self, payload: QuestionCreate) -> Question:
        section = await self.get_section(payload.section_id)
        if not DocSectionType(section.type).holds_questions:
            raise BadRequestError(
                f"A '{section.type}' section holds no questions — use a 'questions' section."
            )
        # Empty collection assigned for the same reason as in ``create_section``.
        return await self.docs.add_question(
            Question(**payload.model_dump(), answer_templates=[])
        )

    async def update_question(self, question_id: uuid.UUID, payload: QuestionUpdate) -> Question:
        question = await self.get_question(question_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(question, field, value)
        return question

    async def delete_question(self, question_id: uuid.UUID) -> None:
        question = await self.get_question(question_id)
        await self.docs.delete_question(question)

    # --- Answer templates ---------------------------------------------------

    async def create_answer(
        self, question_id: uuid.UUID, payload: AnswerTemplateCreate
    ) -> AnswerTemplate:
        await self.get_question(question_id)
        return await self.docs.add_answer(
            AnswerTemplate(question_id=question_id, **payload.model_dump())
        )

    async def get_answer(self, answer_id: uuid.UUID) -> AnswerTemplate:
        answer = await self.docs.get_answer(answer_id)
        if answer is None:
            raise NotFoundError("Answer template not found")
        return answer

    async def update_answer(
        self, answer_id: uuid.UUID, payload: AnswerTemplateUpdate
    ) -> AnswerTemplate:
        answer = await self.get_answer(answer_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(answer, field, value)
        return answer

    async def delete_answer(self, answer_id: uuid.UUID) -> None:
        await self.docs.delete_answer(await self.get_answer(answer_id))
