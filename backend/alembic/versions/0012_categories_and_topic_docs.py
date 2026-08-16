"""categories + structured topic documentation

Replaces the flat ``documents`` table and the ``topics.sample_questions`` JSON
column with the structured model from PRD §8.1/§8.2:

    categories
    topics.category_id / cover_image_url / sort_order
    docs -> doc_sections -> doc_items
                         -> questions -> answer_templates

Existing content is carried over, not dropped:

* Every topic that had documents or sample questions gets a published doc.
* Each old document becomes one section. Its ``kind`` decides the section type —
  ``tip``/``mistake`` become ``tips``, everything else becomes ``text``. Both
  types render ``body``, so the old title and content survive verbatim. Old
  ``vocabulary`` documents are *not* split into ``doc_items``; guessing word
  boundaries from free text would lose data, so an admin re-enters them as items
  when they want the richer card layout.
* ``sample_questions`` becomes a trailing ``questions`` section, one row each.

The downgrade rebuilds the old tables and folds the tree back down: ``text`` and
``tips`` sections return as documents, ``questions`` sections return as
``sample_questions``. Vocabulary/phrase items have no home in the old schema and
are lost — the downgrade is a safety valve, not a round trip.

Revision ID: 0012_categories_and_topic_docs
Revises: 0011_room_password
Create Date: 2026-08-16

"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_categories_and_topic_docs"
down_revision: str | None = "0011_room_password"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Old ``documents.kind`` -> new ``doc_sections.type``. Both targets render the
# section's ``body``, so no content is lost in the move.
_KIND_TO_SECTION_TYPE = {
    "tip": "tips",
    "mistake": "tips",
}
_DEFAULT_SECTION_TYPE = "text"

_QUESTIONS_SECTION_TITLE = "Conversation questions"


def _is_sqlite() -> bool:
    """SQLite can't ``ALTER TABLE ADD CONSTRAINT``.

    The dev database is SQLite and the production one is Postgres, so the foreign
    key is created only where it can be. Nothing is lost in dev: SQLite doesn't
    enforce foreign keys by default here, and the service layer already validates
    every link explicitly for exactly that reason.
    """
    return op.get_bind().dialect.name == "sqlite"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.add_column("topics", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.add_column("topics", sa.Column("cover_image_url", sa.String(length=500), nullable=True))
    op.add_column(
        "topics", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_index("ix_topics_category_id", "topics", ["category_id"])
    if not _is_sqlite():
        op.create_foreign_key(
            "fk_topics_category_id",
            "topics",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "docs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("level", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique, not just indexed: a topic has at most one doc (PRD §8.2).
    op.create_index("ix_docs_topic_id", "docs", ["topic_id"], unique=True)

    op.create_table(
        "doc_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["doc_id"], ["docs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_sections_doc_id", "doc_sections", ["doc_id"])

    op.create_table(
        "doc_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("phonetic", sa.String(length=200), nullable=True),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["section_id"], ["doc_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_items_section_id", "doc_items", ["section_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["section_id"], ["doc_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_section_id", "questions", ["section_id"])

    op.create_table(
        "answer_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_templates_question_id", "answer_templates", ["question_id"])

    _migrate_content_into_docs()

    op.drop_index("ix_documents_topic_id", table_name="documents")
    op.drop_table("documents")
    op.drop_column("topics", "sample_questions")


def downgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), server_default="explanation", nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_topic_id", "documents", ["topic_id"])
    op.add_column(
        "topics",
        sa.Column("sample_questions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )

    _migrate_docs_back()

    op.drop_index("ix_answer_templates_question_id", table_name="answer_templates")
    op.drop_table("answer_templates")
    op.drop_index("ix_questions_section_id", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_doc_items_section_id", table_name="doc_items")
    op.drop_table("doc_items")
    op.drop_index("ix_doc_sections_doc_id", table_name="doc_sections")
    op.drop_table("doc_sections")
    op.drop_index("ix_docs_topic_id", table_name="docs")
    op.drop_table("docs")

    if not _is_sqlite():
        op.drop_constraint("fk_topics_category_id", "topics", type_="foreignkey")
    op.drop_index("ix_topics_category_id", table_name="topics")
    op.drop_column("topics", "sort_order")
    op.drop_column("topics", "cover_image_url")
    op.drop_column("topics", "category_id")
    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_table("categories")


# --- Data migration helpers -------------------------------------------------
#
# These use lightweight ``sa.table`` constructs rather than raw SQL so SQLAlchemy
# applies the ``Uuid`` type binding, which is stored differently on SQLite (a
# 32-char hex string) than on Postgres (a native uuid).


def _lightweight_tables() -> dict[str, sa.TableClause]:
    return {
        "topics": sa.table(
            "topics",
            sa.column("id", sa.Uuid()),
            sa.column("title", sa.String()),
            sa.column("sample_questions", sa.JSON()),
        ),
        "documents": sa.table(
            "documents",
            sa.column("id", sa.Uuid()),
            sa.column("topic_id", sa.Uuid()),
            sa.column("kind", sa.String()),
            sa.column("title", sa.String()),
            sa.column("content", sa.Text()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        "docs": sa.table(
            "docs",
            sa.column("id", sa.Uuid()),
            sa.column("topic_id", sa.Uuid()),
            sa.column("title", sa.String()),
            sa.column("status", sa.String()),
        ),
        "doc_sections": sa.table(
            "doc_sections",
            sa.column("id", sa.Uuid()),
            sa.column("doc_id", sa.Uuid()),
            sa.column("type", sa.String()),
            sa.column("title", sa.String()),
            sa.column("body", sa.Text()),
            sa.column("sort_order", sa.Integer()),
        ),
        "questions": sa.table(
            "questions",
            sa.column("id", sa.Uuid()),
            sa.column("section_id", sa.Uuid()),
            sa.column("text", sa.Text()),
            sa.column("sort_order", sa.Integer()),
        ),
    }


def _as_question_list(raw: object) -> list[str]:
    """Read ``topics.sample_questions`` from either backend.

    Postgres hands back a parsed list; SQLite hands back the raw JSON string.
    Anything unreadable is treated as "no questions" rather than failing the
    whole migration.
    """
    if isinstance(raw, list):
        return [str(q) for q in raw if str(q).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [str(q) for q in parsed if str(q).strip()]
    return []


def _migrate_content_into_docs() -> None:
    conn = op.get_bind()
    t = _lightweight_tables()

    topics = conn.execute(
        sa.select(t["topics"].c.id, t["topics"].c.title, t["topics"].c.sample_questions)
    ).all()
    if not topics:
        return

    documents_by_topic: dict[uuid.UUID, list[sa.Row]] = {}
    for row in conn.execute(
        sa.select(
            t["documents"].c.topic_id,
            t["documents"].c.kind,
            t["documents"].c.title,
            t["documents"].c.content,
        ).order_by(t["documents"].c.created_at)
    ):
        documents_by_topic.setdefault(row.topic_id, []).append(row)

    docs: list[dict] = []
    sections: list[dict] = []
    questions: list[dict] = []

    for topic_id, topic_title, raw_questions in topics:
        old_docs = documents_by_topic.get(topic_id, [])
        sample_questions = _as_question_list(raw_questions)
        if not old_docs and not sample_questions:
            continue  # nothing to carry over — the topic simply has no doc yet

        doc_id = uuid.uuid4()
        docs.append(
            {
                "id": doc_id,
                "topic_id": topic_id,
                "title": topic_title,
                # The old content was already live, so the new doc is published.
                "status": "published",
            }
        )

        order = 0
        for old in old_docs:
            sections.append(
                {
                    "id": uuid.uuid4(),
                    "doc_id": doc_id,
                    "type": _KIND_TO_SECTION_TYPE.get(old.kind, _DEFAULT_SECTION_TYPE),
                    "title": old.title,
                    "body": old.content,
                    "sort_order": order,
                }
            )
            order += 1

        if sample_questions:
            section_id = uuid.uuid4()
            sections.append(
                {
                    "id": section_id,
                    "doc_id": doc_id,
                    "type": "questions",
                    "title": _QUESTIONS_SECTION_TITLE,
                    "body": None,
                    "sort_order": order,
                }
            )
            questions.extend(
                {
                    "id": uuid.uuid4(),
                    "section_id": section_id,
                    "text": text,
                    "sort_order": index,
                }
                for index, text in enumerate(sample_questions)
            )

    if docs:
        conn.execute(t["docs"].insert(), docs)
    if sections:
        conn.execute(t["doc_sections"].insert(), sections)
    if questions:
        conn.execute(t["questions"].insert(), questions)


def _migrate_docs_back() -> None:
    conn = op.get_bind()
    t = _lightweight_tables()

    rows = conn.execute(
        sa.select(
            t["docs"].c.topic_id,
            t["doc_sections"].c.id,
            t["doc_sections"].c.type,
            t["doc_sections"].c.title,
            t["doc_sections"].c.body,
        )
        .select_from(t["doc_sections"].join(t["docs"], t["doc_sections"].c.doc_id == t["docs"].c.id))
        .order_by(t["doc_sections"].c.sort_order)
    ).all()

    documents: list[dict] = []
    questions_by_topic: dict[uuid.UUID, list[str]] = {}

    for topic_id, section_id, section_type, title, body in rows:
        if section_type == "questions":
            texts = conn.execute(
                sa.select(t["questions"].c.text)
                .where(t["questions"].c.section_id == section_id)
                .order_by(t["questions"].c.sort_order)
            ).scalars().all()
            questions_by_topic.setdefault(topic_id, []).extend(texts)
        elif body:
            documents.append(
                {
                    "id": uuid.uuid4(),
                    "topic_id": topic_id,
                    "kind": "tip" if section_type == "tips" else "explanation",
                    "title": title or "Untitled",
                    "content": body,
                }
            )

    if documents:
        conn.execute(
            sa.table(
                "documents",
                sa.column("id", sa.Uuid()),
                sa.column("topic_id", sa.Uuid()),
                sa.column("kind", sa.String()),
                sa.column("title", sa.String()),
                sa.column("content", sa.Text()),
            ).insert(),
            documents,
        )
    for topic_id, texts in questions_by_topic.items():
        conn.execute(
            sa.update(t["topics"])
            .where(t["topics"].c.id == topic_id)
            # The column is typed JSON, so hand it the list — SQLAlchemy encodes it.
            .values(sample_questions=texts)
        )
