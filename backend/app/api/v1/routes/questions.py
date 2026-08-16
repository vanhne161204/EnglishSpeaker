"""Question and answer-template endpoints (PRD §8.2, §8.12).

Questions live inside a doc's ``questions`` section, but they get their own
resource because Warm-up Practice reads them flat, across many topics, without
walking each doc tree.

Path layout — the fixed segment always comes before the id, so a 3-segment path
like ``/questions/answers/{id}`` never collides with ``/questions/{id}``:

    /questions                          list (flat, published docs only), create
    /questions/{question_id}            edit, delete
    /questions/{question_id}/answers    add an answer template
    /questions/answers/{answer_id}      edit, delete an answer template
"""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_doc_service, require_admin
from app.models.doc import AnswerTemplate, Question
from app.models.user import User
from app.schemas.doc import (
    AnswerTemplateCreate,
    AnswerTemplateRead,
    AnswerTemplateUpdate,
    QuestionCreate,
    QuestionRead,
    QuestionUpdate,
    TopicQuestionRead,
)
from app.services.doc import DocService

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get(
    "",
    response_model=list[TopicQuestionRead],
    summary="List questions from published docs (optionally one topic)",
)
async def list_questions(
    topic_id: uuid.UUID | None = None,
    service: DocService = Depends(get_doc_service),
) -> list[TopicQuestionRead]:
    # Draft and archived docs are skipped, so unfinished content never reaches a learner.
    return await service.list_topic_questions(topic_id)


@router.post(
    "",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a question to a 'questions' section (admin)",
)
async def create_question(
    payload: QuestionCreate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> Question:
    # 400 if the target section is not a 'questions' section.
    return await service.create_question(payload)


@router.patch("/{question_id}", response_model=QuestionRead, summary="Edit a question (admin)")
async def update_question(
    question_id: uuid.UUID,
    payload: QuestionUpdate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> Question:
    return await service.update_question(question_id, payload)


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a question and its answer templates (admin)",
)
async def delete_question(
    question_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_question(question_id)


@router.post(
    "/{question_id}/answers",
    response_model=AnswerTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a sample answer template to a question (admin)",
)
async def create_answer(
    question_id: uuid.UUID,
    payload: AnswerTemplateCreate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> AnswerTemplate:
    return await service.create_answer(question_id, payload)


@router.patch(
    "/answers/{answer_id}",
    response_model=AnswerTemplateRead,
    summary="Edit an answer template (admin)",
)
async def update_answer(
    answer_id: uuid.UUID,
    payload: AnswerTemplateUpdate,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> AnswerTemplate:
    return await service.update_answer(answer_id, payload)


@router.delete(
    "/answers/{answer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an answer template (admin)",
)
async def delete_answer(
    answer_id: uuid.UUID,
    service: DocService = Depends(get_doc_service),
    _: User = Depends(require_admin),
) -> None:
    await service.delete_answer(answer_id)
