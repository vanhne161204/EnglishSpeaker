"""Idempotent demo seeding so the app shows content on first run."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Required, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.doc import AnswerTemplate, Doc, DocItem, DocSection, Question
from app.models.message import Message
from app.models.room import Room
from app.models.sentence_note import SentenceNote
from app.models.topic import Topic
from app.models.user import User

logger = logging.getLogger(__name__)


class QuestionSpec(TypedDict, total=False):
    """One seeded question. ``answers`` become its answer templates (PRD §8.2)."""

    text: Required[str]
    answers: list[dict[str, str]]


class SectionSpec(TypedDict, total=False):
    """One seeded doc section. ``type`` decides which of the other keys apply."""

    type: Required[str]
    title: str
    body: str
    items: list[dict[str, str]]
    questions: list[QuestionSpec]


class DocSpec(TypedDict, total=False):
    """One seeded topic doc, matched to its topic by ``topic_slug``."""

    topic_slug: Required[str]
    intro: str
    sections: list[SectionSpec]


# Categories group topics into themes (PRD §8.1).
DEMO_CATEGORIES: list[dict[str, object]] = [
    {
        "slug": "daily-life",
        "name": "Daily Life",
        "description": "Everyday routines, food, and small talk.",
        "sort_order": 0,
    },
    {
        "slug": "work",
        "name": "Work",
        "description": "Interviews, meetings, and the language of the office.",
        "sort_order": 1,
    },
    {
        "slug": "travel",
        "name": "Travel",
        "description": "Airports, hotels, and finding your way around.",
        "sort_order": 2,
    },
]

DEMO_TOPICS: list[dict[str, object]] = [
    {
        "slug": "daily-life",
        "title": "Daily Life",
        "description": "Talk about your everyday routine and habits.",
        "level": "beginner",
        "category_slug": "daily-life",
        "sort_order": 0,
    },
    {
        "slug": "food",
        "title": "Food",
        "description": "Discuss favourite dishes and cooking.",
        "level": "beginner",
        "category_slug": "daily-life",
        "sort_order": 1,
    },
    {
        "slug": "travel",
        "title": "Travel",
        "description": "Share travel stories, plans, and tips.",
        "level": "intermediate",
        "category_slug": "travel",
        "sort_order": 0,
    },
    {
        "slug": "job-interview",
        "title": "Job Interview",
        "description": "Practice common interview questions and answers.",
        "level": "advanced",
        "category_slug": "work",
        "sort_order": 0,
    },
    {
        "slug": "technology",
        "title": "Technology",
        "description": "Talk about gadgets, apps, and trends.",
        "level": "intermediate",
        "category_slug": "work",
        "sort_order": 1,
    },
]

# One doc per topic (PRD §8.2). A section's `type` decides which key it uses:
# `items` for vocabulary/phrases, `questions` for questions, `body` for tips/text.
DEMO_DOCS: list[DocSpec] = [
    {
        "topic_slug": "daily-life",
        "intro": "Read the words and questions below, then join a room and talk about your day.",
        "sections": [
            {
                "type": "vocabulary",
                "title": "Everyday words",
                "items": [
                    {
                        "term": "breakfast",
                        "phonetic": "/ˈbrekfəst/",
                        "meaning": "the first meal of the day",
                        "example": "I have breakfast at seven o'clock.",
                    },
                    {
                        "term": "commute",
                        "phonetic": "/kəˈmjuːt/",
                        "meaning": "the trip between home and work",
                        "example": "My commute takes forty minutes.",
                    },
                    {
                        "term": "chore",
                        "phonetic": "/tʃɔːr/",
                        "meaning": "a small job you do at home",
                        "example": "Washing up is my least favourite chore.",
                    },
                ],
            },
            {
                "type": "questions",
                "title": "Conversation questions",
                "questions": [
                    {
                        "text": "Walk me through a normal morning for you.",
                        "answers": [
                            {
                                "template": "I usually wake up at ___ and then I ___.",
                                "example": "I usually wake up at six and then I make coffee.",
                            }
                        ],
                    },
                    {
                        "text": "What is one small thing that always makes your day better?",
                        "answers": [
                            {
                                "template": "___ always makes my day better because ___.",
                                "example": "A short walk always makes my day better "
                                "because it clears my head.",
                            }
                        ],
                    },
                    {"text": "How do you usually spend your evenings after work or study?"},
                    {"text": "Is there a habit you would like to start? Tell me about it."},
                    {"text": "What did you have for your last meal, and did you like it?"},
                ],
            },
            {
                "type": "tips",
                "title": "Speaking tips",
                "body": (
                    "Use the present simple for routines: 'I get up at seven', not "
                    "'I am getting up at seven'. Add a time word — usually, always, "
                    "every day — and your answer sounds twice as natural."
                ),
            },
        ],
    },
    {
        "topic_slug": "food",
        "intro": "Words, phrases, and questions for talking about what you eat.",
        "sections": [
            {
                "type": "phrases",
                "title": "Useful phrases",
                "items": [
                    {
                        "term": "I'm not a big fan of ___",
                        "meaning": "a polite way to say you dislike something",
                        "example": "I'm not a big fan of spicy food.",
                    },
                    {
                        "term": "It tastes a bit like ___",
                        "meaning": "compare a new food to a familiar one",
                        "example": "It tastes a bit like chicken.",
                    },
                ],
            },
            {
                "type": "questions",
                "title": "Conversation questions",
                "questions": [
                    {
                        "text": "What is your favourite dish, and how does it taste?",
                        "answers": [
                            {
                                "template": "My favourite dish is ___. It tastes ___.",
                                "example": "My favourite dish is pho. It tastes fresh and savoury.",
                            }
                        ],
                    },
                    {"text": "Describe a meal you could eat every day without getting bored."},
                    {"text": "Do you like cooking? Tell me about the last thing you made."},
                    {"text": "What food from another country would you like to try?"},
                    {"text": "Describe your perfect breakfast in as much detail as you can."},
                ],
            },
        ],
    },
    {
        "topic_slug": "travel",
        "intro": "The words you need at an airport, a hotel, and everywhere in between.",
        "sections": [
            {
                "type": "vocabulary",
                "title": "Useful travel words",
                "items": [
                    {
                        "term": "itinerary",
                        "phonetic": "/aɪˈtɪnərəri/",
                        "meaning": "the plan of a trip",
                        "example": "Our itinerary has three cities in five days.",
                    },
                    {
                        "term": "boarding pass",
                        "meaning": "the ticket you show to get on a plane",
                        "example": "Keep your boarding pass in your pocket.",
                    },
                    {
                        "term": "layover",
                        "phonetic": "/ˈleɪoʊvər/",
                        "meaning": "a wait between two flights",
                        "example": "We have a two-hour layover in Singapore.",
                    },
                    {
                        "term": "sightseeing",
                        "meaning": "visiting interesting places as a tourist",
                        "example": "We spent the morning sightseeing.",
                    },
                ],
            },
            {
                "type": "questions",
                "title": "Conversation questions",
                "questions": [
                    {
                        "text": "What is a place you have always wanted to visit, and why?",
                        "answers": [
                            {
                                "template": "I've always wanted to visit ___ because ___.",
                                "example": "I've always wanted to visit Iceland "
                                "because I want to see the northern lights.",
                            }
                        ],
                    },
                    {"text": "Tell me about a trip that you remember well."},
                    {"text": "Do you prefer the mountains or the sea? Explain your choice."},
                    {"text": "What do you usually pack when you travel somewhere new?"},
                    {"text": "Describe your ideal weekend trip from start to finish."},
                ],
            },
        ],
    },
    {
        "topic_slug": "job-interview",
        "intro": "Interview questions, with a sentence shape for each of the hard ones.",
        "sections": [
            {
                "type": "questions",
                "title": "Conversation questions",
                "questions": [
                    {
                        "text": "Tell me a little about yourself and your background.",
                        "answers": [
                            {
                                "template": "I'm a ___ with ___ years of experience in ___. "
                                "I enjoy ___, and I'm looking for a role where I can ___.",
                                "example": "I'm a designer with four years of experience in "
                                "mobile apps. I enjoy user research, and I'm looking for a "
                                "role where I can lead a small team.",
                            }
                        ],
                    },
                    {
                        "text": "Describe a challenge you faced and how you handled it.",
                        "answers": [
                            {
                                "template": "The situation was ___. My task was ___. "
                                "I ___, and in the end ___.",
                                "example": "The situation was a deadline moving up by a week. "
                                "My task was to ship the login screen. I cut the animation "
                                "work, and in the end we shipped on time.",
                            }
                        ],
                    },
                    {"text": "What are you good at? Give an example from your experience."},
                    {"text": "Why do you want this role, and what interests you about it?"},
                    {"text": "Where would you like to be in your career in a few years?"},
                ],
            },
            {
                "type": "tips",
                "title": "Use the STAR method",
                "body": (
                    "Answer behaviour questions with Situation, Task, Action, Result. "
                    "It keeps a long answer in order, and the interviewer can follow you "
                    "even if your grammar slips."
                ),
            },
        ],
    },
    {
        "topic_slug": "technology",
        "intro": "Talk about the apps and devices you use every day.",
        "sections": [
            {
                "type": "questions",
                "title": "Conversation questions",
                "questions": [
                    {
                        "text": "What app or device could you not live without, and why?",
                        "answers": [
                            {
                                "template": "I couldn't live without ___ because I use it to ___.",
                                "example": "I couldn't live without my headphones "
                                "because I use them to focus at work.",
                            }
                        ],
                    },
                    {"text": "Tell me about a piece of technology you learned to use recently."},
                    {"text": "How do you think phones have changed the way we talk to people?"},
                    {"text": "Is there a new technology you are excited or worried about?"},
                    {"text": "Describe how you would explain the internet to a young child."},
                ],
            },
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
        if not await session.scalar(select(func.count()).select_from(Category)):
            session.add_all([Category(**c) for c in DEMO_CATEGORIES])
            logger.info("Seeded %d demo categories", len(DEMO_CATEGORIES))

        # Topics reference categories by slug, so categories must have ids first.
        await session.flush()

        if not await session.scalar(select(func.count()).select_from(Topic)):
            await _seed_topics(session)

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

        if not await session.scalar(select(func.count()).select_from(Doc)):
            await _seed_docs(session)

        await session.commit()


async def _seed_topics(session: AsyncSession) -> None:
    """Add the demo topics, resolving each one's category by slug."""
    categories = (await session.execute(select(Category))).scalars().all()
    by_slug = {c.slug: c for c in categories}
    for spec in DEMO_TOPICS:
        data = dict(spec)
        category = by_slug.get(str(data.pop("category_slug", "")))
        session.add(Topic(**data, category_id=category.id if category else None))
    logger.info("Seeded %d demo topics", len(DEMO_TOPICS))


async def _seed_docs(session: AsyncSession) -> None:
    """Build each topic's documentation tree (PRD §8.2), matched by topic slug."""
    topics = (await session.execute(select(Topic))).scalars().all()
    by_slug = {t.slug: t for t in topics}
    seeded = 0
    for spec in DEMO_DOCS:
        topic = by_slug.get(str(spec["topic_slug"]))
        if topic is None:
            continue
        # Cascades save the whole tree, so only the doc needs adding to the session.
        session.add(_build_doc(topic, spec))
        seeded += 1
    if seeded:
        logger.info("Seeded documentation for %d topics", seeded)


def _build_doc(topic: Topic, spec: DocSpec) -> Doc:
    sections: list[DocSection] = []
    for order, section_spec in enumerate(spec.get("sections", [])):
        section = DocSection(
            type=section_spec["type"],
            title=section_spec.get("title"),
            body=section_spec.get("body"),
            sort_order=order,
        )
        section.items = [
            DocItem(**item, sort_order=index)
            for index, item in enumerate(section_spec.get("items", []))
        ]
        section.questions = [
            _build_question(question, index)
            for index, question in enumerate(section_spec.get("questions", []))
        ]
        sections.append(section)

    return Doc(
        topic_id=topic.id,
        title=topic.title,
        intro=spec.get("intro"),
        level=topic.level,
        # Demo content is finished content, so it is visible to learners right away.
        status="published",
        sections=sections,
    )


def _build_question(spec: QuestionSpec, order: int) -> Question:
    question = Question(text=spec["text"], sort_order=order)
    question.answer_templates = [
        AnswerTemplate(**answer, sort_order=index)
        for index, answer in enumerate(spec.get("answers", []))
    ]
    return question


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
