"""Aggregates all v1 routers into a single router mounted under the API prefix."""

from fastapi import APIRouter

from app.api.v1.routes import (
    assist,
    auth,
    categories,
    docs,
    feedback,
    health,
    match,
    notes,
    questions,
    reports,
    rooms,
    topics,
    transcription,
    transcripts,
    translation,
    users,
    voice_ws,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(topics.router)
api_router.include_router(docs.router)
api_router.include_router(questions.router)
api_router.include_router(rooms.router)
api_router.include_router(notes.router)
api_router.include_router(translation.router)
api_router.include_router(transcription.router)
api_router.include_router(transcripts.router)
api_router.include_router(users.router)
api_router.include_router(match.router)
api_router.include_router(assist.router)
api_router.include_router(feedback.router)
api_router.include_router(reports.router)
api_router.include_router(ws.router)
api_router.include_router(voice_ws.router)
