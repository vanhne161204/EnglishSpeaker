"""Idempotent demo seeding so the app shows content on first run."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.models.message import Message
from app.models.room import Room
from app.models.sentence_note import SentenceNote
from app.models.topic import Topic
from app.models.user import User

logger = logging.getLogger(__name__)

DEMO_TOPICS: list[dict[str, object]] = [
    {
        "slug": "daily-life",
        "title": "Daily Life",
        "description": "Talk about your everyday routine and habits.",
        "level": "beginner",
        "sample_questions": [
            "Walk me through a normal morning for you.",
            "What is one small thing that always makes your day better?",
            "How do you usually spend your evenings after work or study?",
            "Is there a habit you would like to start? Tell me about it.",
            "What did you have for your last meal, and did you like it?",
        ],
    },
    {
        "slug": "travel",
        "title": "Travel",
        "description": "Share travel stories, plans, and tips.",
        "level": "intermediate",
        "sample_questions": [
            "What is a place you have always wanted to visit, and why?",
            "Tell me about a trip that you remember well.",
            "Do you prefer the mountains or the sea? Explain your choice.",
            "What do you usually pack when you travel somewhere new?",
            "Describe your ideal weekend trip from start to finish.",
        ],
    },
    {
        "slug": "food",
        "title": "Food",
        "description": "Discuss favourite dishes and cooking.",
        "level": "beginner",
        "sample_questions": [
            "What is your favourite dish, and how does it taste?",
            "Describe a meal you could eat every day without getting bored.",
            "Do you like cooking? Tell me about the last thing you made.",
            "What food from another country would you like to try?",
            "Describe your perfect breakfast in as much detail as you can.",
        ],
    },
    {
        "slug": "job-interview",
        "title": "Job Interview",
        "description": "Practice common interview questions and answers.",
        "level": "advanced",
        "sample_questions": [
            "Tell me a little about yourself and your background.",
            "What are you good at? Give an example from your experience.",
            "Describe a challenge you faced and how you handled it.",
            "Why do you want this role, and what interests you about it?",
            "Where would you like to be in your career in a few years?",
        ],
    },
    {
        "slug": "technology",
        "title": "Technology",
        "description": "Talk about gadgets, apps, and trends.",
        "level": "intermediate",
        "sample_questions": [
            "What app or device could you not live without, and why?",
            "Tell me about a piece of technology you learned to use recently.",
            "How do you think phones have changed the way we talk to people?",
            "Is there a new technology you are excited or worried about?",
            "Describe how you would explain the internet to a young child.",
        ],
    },
]

DEMO_ROOMS: list[dict[str, object]] = [
    # Normal-mode group rooms
    {
        "title": "Morning Coffee Chat",
        "mode": "normal",
        "kind": "group",
        "topic": "Daily Life",
        "level": "beginner",
        "capacity": 4,
        "participant_count": 2,
    },
    {
        "title": "Travel Buddies",
        "mode": "normal",
        "kind": "group",
        "topic": "Travel",
        "level": "intermediate",
        "capacity": 4,
        "participant_count": 3,
    },
    {
        "title": "Tech Talk",
        "mode": "normal",
        "kind": "group",
        "topic": "Technology",
        "level": "advanced",
        "capacity": 4,
        "participant_count": 1,
    },
    # Normal-mode 1-on-1 rooms (a room that seats two)
    {
        "title": "1-on-1: Job Interview Practice",
        "mode": "normal",
        "kind": "one_on_one",
        "topic": "Job Interview",
        "level": "intermediate",
        "capacity": 2,
        "participant_count": 1,
    },
    {
        "title": "1-on-1: Free Talk",
        "mode": "normal",
        "kind": "one_on_one",
        "topic": "Daily Life",
        "level": "beginner",
        "capacity": 2,
        "participant_count": 1,
    },
    # Incognito-mode group rooms
    {
        "title": "Anonymous Practice",
        "mode": "incognito",
        "kind": "group",
        "topic": "Daily Life",
        "level": "beginner",
        "capacity": 4,
        "participant_count": 2,
    },
    {
        "title": "Shy Speakers Lounge",
        "mode": "incognito",
        "kind": "group",
        "topic": "Small Talk",
        "level": "beginner",
        "capacity": 6,
        "participant_count": 4,
    },
    # Incognito-mode 1-on-1 room
    {
        "title": "1-on-1: Private Interview Prep",
        "mode": "incognito",
        "kind": "one_on_one",
        "topic": "Job Interview",
        "level": "advanced",
        "capacity": 2,
        "participant_count": 1,
    },
]

# `password` here is plaintext for seeding convenience only — it is hashed before
# it ever reaches the database (see the seed loop). Handy demo logins:
#   username "maya" / password "practice123", username "leo" / password "practice123".
DEMO_USERS: list[dict[str, str]] = [
    {
        "display_name": "Maya",
        "username": "maya",
        "password": "practice123",
        "level": "intermediate",
        "interests": "travel,food",
    },
    {
        "display_name": "Leo",
        "username": "leo",
        "password": "practice123",
        "level": "beginner",
        "interests": "music,movies",
    },
]

# A short scripted exchange so the first room a user opens already has life in it.
DEMO_CONVERSATION: dict[str, object] = {
    "room_title": "Morning Coffee Chat",
    "lines": [
        ("Maya", "Good morning! How is everyone today?"),
        ("Leo", "Morning! I'm good, just had my coffee."),
        ("Maya", "Same here. What did you do this weekend?"),
    ],
}

# Admin learning content (PRD §8.2), keyed by topic slug.
DEMO_DOCUMENTS: list[dict[str, str]] = [
    {
        "topic_slug": "travel",
        "kind": "vocabulary",
        "title": "Useful travel words",
        "content": (
            "itinerary, boarding pass, layover, sightseeing, local cuisine, "
            "currency exchange"
        ),
    },
    {
        "topic_slug": "travel",
        "kind": "example",
        "title": "Questions to ask",
        "content": (
            "Where would you like to travel next? "
            "What is the most memorable trip you have taken?"
        ),
    },
    {
        "topic_slug": "job-interview",
        "kind": "sample_answer",
        "title": "Tell me about yourself",
        "content": (
            "I'm a <role> with <n> years of experience in <field>. I enjoy <skill>, "
            "and I'm looking for a role where I can <goal>."
        ),
    },
    {
        "topic_slug": "job-interview",
        "kind": "tip",
        "title": "Use the STAR method",
        "content": "Answer behaviour questions with Situation, Task, Action, Result.",
    },
]

DEMO_NOTES: list[dict[str, str]] = [
    {
        "original_text": "I very like travel.",
        "improved_text": "I really enjoy travelling.",
        "source": "ai",
        "topic": "Travel",
    },
    {
        "original_text": "He don't have time.",
        "improved_text": "He doesn't have time.",
        "source": "ai",
        "topic": "Daily Life",
    },
]


async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as session:
        if not await session.scalar(select(func.count()).select_from(Topic)):
            session.add_all([Topic(**t) for t in DEMO_TOPICS])
            logger.info("Seeded %d demo topics", len(DEMO_TOPICS))

        if not await session.scalar(select(func.count()).select_from(Room)):
            session.add_all([Room(**r) for r in DEMO_ROOMS])
            logger.info("Seeded %d demo rooms", len(DEMO_ROOMS))

        if not await session.scalar(select(func.count()).select_from(SentenceNote)):
            session.add_all([SentenceNote(**n) for n in DEMO_NOTES])
            logger.info("Seeded %d demo notes", len(DEMO_NOTES))

        if not await session.scalar(select(func.count()).select_from(User)):
            session.add_all(
                [
                    User(**{k: v for k, v in u.items() if k != "password"},
                         password_hash=hash_password(u["password"]))
                    for u in DEMO_USERS
                ]
            )
            logger.info("Seeded %d demo users", len(DEMO_USERS))

        # Flush so seeded topics/users/rooms have ids before wiring up dependents.
        await session.flush()

        if not await session.scalar(select(func.count()).select_from(Message)):
            await _seed_conversation(session)

        if not await session.scalar(select(func.count()).select_from(Document)):
            await _seed_documents(session)

        await session.commit()


async def _seed_documents(session: AsyncSession) -> None:
    """Attach a few admin learning documents to their topics by slug."""
    topics = (await session.execute(select(Topic))).scalars().all()
    by_slug = {t.slug: t for t in topics}
    seeded = 0
    for doc in DEMO_DOCUMENTS:
        topic = by_slug.get(doc["topic_slug"])
        if topic is None:
            continue
        session.add(
            Document(
                topic_id=topic.id,
                kind=doc["kind"],
                title=doc["title"],
                content=doc["content"],
            )
        )
        seeded += 1
    if seeded:
        logger.info("Seeded %d demo documents", seeded)


async def _seed_conversation(session: AsyncSession) -> None:
    """Add a scripted exchange to one room so it isn't empty on first open."""
    room = await session.scalar(
        select(Room).where(Room.title == DEMO_CONVERSATION["room_title"])
    )
    if room is None:
        return

    users = (await session.execute(select(User))).scalars().all()
    by_name = {u.display_name: u for u in users}

    lines: list[tuple[str, str]] = DEMO_CONVERSATION["lines"]  # type: ignore[assignment]
    # Stagger timestamps so the scripted lines always read in order (SQLite's
    # CURRENT_TIMESTAMP is only second-resolution, so equal times would tie).
    base = datetime.now(UTC) - timedelta(minutes=len(lines))
    seeded = 0
    for offset, (sender_name, text) in enumerate(lines):
        user = by_name.get(sender_name)
        if user is None:
            continue
        session.add(
            Message(
                room_id=room.id,
                user_id=user.id,
                sender_name=sender_name,
                text=text,
                created_at=base + timedelta(minutes=offset),
            )
        )
        seeded += 1
    if seeded:
        logger.info("Seeded %d demo messages", seeded)
