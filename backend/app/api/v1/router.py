"""Aggregates all v1 routers into a single router mounted under the API prefix."""

from fastapi import APIRouter

from app.api.v1.routes import (
    assist,
    auth,
    documents,
    health,
    match,
    notes,
    rooms,
    topics,
    transcription,
    translation,
    users,
    voice_ws,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(topics.router)
api_router.include_router(documents.router)
api_router.include_router(rooms.router)
api_router.include_router(notes.router)
api_router.include_router(translation.router)
api_router.include_router(transcription.router)
api_router.include_router(users.router)
api_router.include_router(match.router)
api_router.include_router(assist.router)
api_router.include_router(ws.router)
api_router.include_router(voice_ws.router)
