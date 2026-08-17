"""Data-access for topic documentation (PRD §8.2).

One repository covers the whole doc aggregate — doc, sections, items, questions,
answer templates — because they are never read or written independently of the
doc they belong to.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doc import AnswerTemplate, Doc, DocItem, DocSection, Question
from app.models.enums import ContentStatus
from app.models.topic import Topic


class DocRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Docs ---------------------------------------------------------------

    async def list(self, topic_id: uuid.UUID | None = None) -> Sequence[Doc]:
        stmt = select(Doc)
        if topic_id is not None:
            stmt = stmt.where(Doc.topic_id == topic_id)
        stmt = stmt.order_by(Doc.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, doc_id: uuid.UUID) -> Doc | None:
        return await self.session.get(Doc, doc_id)

    async def get_by_topic(self, topic_id: uuid.UUID) -> Doc | None:
        result = await self.session.execute(select(Doc).where(Doc.topic_id == topic_id))
        return result.scalar_one_or_none()

    async def add(self, doc: Doc) -> Doc:
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def delete(self, doc: Doc) -> None:
        await self.session.delete(doc)

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Doc)) or 0

    async def flush(self) -> None:
        """Push pending changes to the database without committing.

        Needed when a caller must sequence deletes before inserts inside one
        request — see ``DocService.replace_qa_pairs``.
        """
        await self.session.flush()

    # --- Sections -----------------------------------------------------------

    async def get_section(self, section_id: uuid.UUID) -> DocSection | None:
        return await self.session.get(DocSection, section_id)

    async def add_section(self, section: DocSection) -> DocSection:
        self.session.add(section)
        await self.session.flush()
        return section

    async def delete_section(self, section: DocSection) -> None:
        await self.session.delete(section)

    # --- Items (vocabulary / phrases) ---------------------------------------

    async def get_item(self, item_id: uuid.UUID) -> DocItem | None:
        return await self.session.get(DocItem, item_id)

    async def add_item(self, item: DocItem) -> DocItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def delete_item(self, item: DocItem) -> None:
        await self.session.delete(item)

    # --- Questions ----------------------------------------------------------

    async def get_question(self, question_id: uuid.UUID) -> Question | None:
        return await self.session.get(Question, question_id)

    async def add_question(self, question: Question) -> Question:
        self.session.add(question)
        await self.session.flush()
        return question

    async def delete_question(self, question: Question) -> None:
        await self.session.delete(question)

    async def list_published_questions(
        self, topic_id: uuid.UUID | None = None
    ) -> Sequence[Row[tuple[Question, uuid.UUID, str]]]:
        """Questions from *published* docs, flattened with their topic.

        Powers Warm-up Practice (PRD §8.12), which needs questions across many
        topics at once. Draft and archived docs are skipped so a half-written doc
        never reaches a learner. Each row is ``(question, topic_id, topic_title)``.
        """
        stmt = (
            select(Question, Topic.id, Topic.title)
            .join(DocSection, Question.section_id == DocSection.id)
            .join(Doc, DocSection.doc_id == Doc.id)
            .join(Topic, Doc.topic_id == Topic.id)
            .where(Doc.status == ContentStatus.published.value)
        )
        if topic_id is not None:
            stmt = stmt.where(Topic.id == topic_id)
        stmt = stmt.order_by(
            Topic.sort_order, Topic.title, DocSection.sort_order, Question.sort_order
        )
        result = await self.session.execute(stmt)
        return result.all()

    # --- Answer templates ---------------------------------------------------

    async def get_answer(self, answer_id: uuid.UUID) -> AnswerTemplate | None:
        return await self.session.get(AnswerTemplate, answer_id)

    async def add_answer(self, answer: AnswerTemplate) -> AnswerTemplate:
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def delete_answer(self, answer: AnswerTemplate) -> None:
        await self.session.delete(answer)
