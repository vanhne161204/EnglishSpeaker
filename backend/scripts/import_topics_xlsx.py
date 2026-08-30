"""Import the curated topic workbook into the EnglishTalker content tables.

Reads ``English_Speaking_Topics_Database.xlsx`` and emits idempotent SQL on
stdout. Nothing is executed here — review the SQL, then pipe it at a database::

    python backend/scripts/import_topics_xlsx.py English_Speaking_Topics_Database.xlsx -o import.sql
    ssh ec2 'docker compose ... exec -T db psql -U englishtalker englishtalker' < import.sql

Workbook sheet      ->  table
    Topics.group        categories
    Topics.topic        topics  (+ one docs row each)
    Vocabulary.word     doc_items         under a 'vocabulary' section
    Questions.question  questions         under a 'questions' section
    Answers.answer      answer_templates

Primary keys are UUIDv5 values derived from a fixed namespace plus the workbook's
own identifiers, so every row has a stable id. Combined with
``ON CONFLICT (id) DO NOTHING`` that makes the import re-runnable: running it
twice inserts the same rows once, and a corrected workbook only adds what is new.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

import openpyxl

# Fixed namespace: changing it would orphan every previously imported row.
NAMESPACE = uuid.UUID("6f1d9e2a-4c58-4b1e-9f3d-2a7c8e5b10d4")

# Sections created for every topic, in display order.
VOCAB_SECTION_ORDER = 0
QUESTION_SECTION_ORDER = 1


def det_id(*parts: object) -> uuid.UUID:
    """Stable UUID for a logical row, so re-imports are idempotent."""
    return uuid.uuid5(NAMESPACE, "|".join(str(part) for part in parts))


def slugify(value: str) -> str:
    """URL-safe slug: lowercase, ampersands spelled out, runs of junk collapsed."""
    text = value.strip().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def sql_str(value: Any) -> str:
    """Quote a value as a SQL literal, or NULL. Doubles embedded quotes."""
    if value is None:
        return "NULL"
    text = str(value).strip()
    if not text:
        return "NULL"
    escaped = text.replace("'", "''")
    return "'" + escaped + "'"


def sql_uuid(value: uuid.UUID | None) -> str:
    """Quote a UUID as a SQL literal, or NULL."""
    return "NULL" if value is None else "'" + str(value) + "'"


def unique_slugs(topic_rows: list[tuple]) -> dict[str, str]:
    """Map each workbook topic_id to a slug that is unique across all topics.

    The workbook lists a few topic names twice under different groups
    ("Transportation" appears under both Daily Life and Travel & Experiences).
    They are genuinely separate topics with their own questions, so they are kept
    apart rather than merged — but ``topics.slug`` is UNIQUE, so the repeats need
    distinguishing. The lowest topic_id keeps the clean slug and the others get
    their topic_id appended. Keying off topic_id rather than row position means
    re-ordering the sheet cannot silently change a published URL.
    """
    by_slug: dict[str, list[str]] = defaultdict(list)
    for topic_id, _group, title in topic_rows:
        by_slug[slugify(str(title).strip())].append(str(topic_id).strip())

    resolved: dict[str, str] = {}
    for slug, topic_ids in by_slug.items():
        if len(topic_ids) == 1:
            resolved[topic_ids[0]] = slug
            continue
        first, *rest = sorted(topic_ids, key=lambda value: (len(value), value))
        resolved[first] = slug
        for topic_id in rest:
            resolved[topic_id] = f"{slug}-{topic_id}"
    return resolved


def rows_of(workbook: openpyxl.Workbook, sheet: str) -> list[tuple]:
    """Data rows of a sheet (header dropped, fully blank rows dropped)."""
    return [
        row
        for row in list(workbook[sheet].iter_rows(values_only=True))[1:]
        if row and any(cell is not None and str(cell).strip() for cell in row)
    ]


def as_int(value: Any) -> int:
    """Sort order from a workbook cell; unreadable values sort first."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def build_sql(path: Path) -> tuple[list[str], dict[str, int], list[str]]:
    """Return (SQL statements, per-table counts, topic slugs) for the workbook."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)

    topic_rows = rows_of(workbook, "Topics")  # topic_id, group, topic
    question_rows = rows_of(workbook, "Questions")  # qid, topic_id, topic, no, question
    answer_rows = rows_of(workbook, "Answers")  # aid, qid, topic_id, answer
    vocab_rows = rows_of(workbook, "Vocabulary")  # vid, topic_id, topic, no, word

    statements: list[str] = ["BEGIN;"]
    counts: dict[str, int] = defaultdict(int)
    slugs: list[str] = []

    # --- categories: one per distinct group, ordered by first appearance ---
    groups: OrderedDict[str, None] = OrderedDict()
    for _, group, _ in topic_rows:
        if group:
            groups.setdefault(str(group).strip(), None)

    for order, group in enumerate(groups):
        statements.append(
            "INSERT INTO categories (id, name, slug, sort_order, created_at, updated_at)"
            " VALUES ("
            + sql_uuid(det_id("category", group))
            + ", "
            + sql_str(group)
            + ", "
            + sql_str(slugify(group))
            + ", "
            + str(order)
            + ", now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["categories"] += 1

    # --- topics, each with one doc and two sections ---
    # Excel topic_id -> the section ids its children hang off.
    vocab_section: dict[str, uuid.UUID] = {}
    question_section: dict[str, uuid.UUID] = {}

    slug_by_topic = unique_slugs(topic_rows)

    for order, (topic_id, group, title) in enumerate(topic_rows):
        topic_key = str(topic_id).strip()
        title = str(title).strip()
        slug = slug_by_topic[topic_key]
        slugs.append(slug)

        category_id = det_id("category", str(group).strip()) if group else None
        topic_pk = det_id("topic", topic_key)
        doc_pk = det_id("doc", topic_key)
        vocab_pk = det_id("section", topic_key, "vocabulary")
        question_pk = det_id("section", topic_key, "questions")
        vocab_section[topic_key] = vocab_pk
        question_section[topic_key] = question_pk

        statements.append(
            "INSERT INTO topics (id, category_id, slug, title, status, sort_order,"
            " created_at, updated_at) VALUES ("
            + sql_uuid(topic_pk)
            + ", "
            + sql_uuid(category_id)
            + ", "
            + sql_str(slug)
            + ", "
            + sql_str(title)
            + ", 'published', "
            + str(order)
            + ", now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["topics"] += 1

        statements.append(
            "INSERT INTO docs (id, topic_id, title, status, created_at, updated_at) VALUES ("
            + sql_uuid(doc_pk)
            + ", "
            + sql_uuid(topic_pk)
            + ", "
            + sql_str(title)
            + ", 'published', now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["docs"] += 1

        sections = (
            (vocab_pk, "vocabulary", "Vocabulary", VOCAB_SECTION_ORDER),
            (question_pk, "questions", "Questions", QUESTION_SECTION_ORDER),
        )
        for section_pk, section_type, section_title, section_order in sections:
            statements.append(
                "INSERT INTO doc_sections (id, doc_id, type, title, sort_order,"
                " created_at, updated_at) VALUES ("
                + sql_uuid(section_pk)
                + ", "
                + sql_uuid(doc_pk)
                + ", "
                + sql_str(section_type)
                + ", "
                + sql_str(section_title)
                + ", "
                + str(section_order)
                + ", now(), now()) ON CONFLICT (id) DO NOTHING;"
            )
            counts["doc_sections"] += 1

    # --- vocabulary items ---
    for vocab_id, topic_id, _topic, number, word in vocab_rows:
        section_pk = vocab_section.get(str(topic_id).strip())
        if section_pk is None or not word:
            continue
        statements.append(
            "INSERT INTO doc_items (id, section_id, term, sort_order, created_at,"
            " updated_at) VALUES ("
            + sql_uuid(det_id("item", vocab_id))
            + ", "
            + sql_uuid(section_pk)
            + ", "
            + sql_str(word)
            + ", "
            + str(as_int(number))
            + ", now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["doc_items"] += 1

    # --- questions ---
    question_ids: dict[str, uuid.UUID] = {}
    for question_id, topic_id, _topic, number, text in question_rows:
        section_pk = question_section.get(str(topic_id).strip())
        if section_pk is None or not text:
            continue
        pk = det_id("question", question_id)
        question_ids[str(question_id).strip()] = pk
        statements.append(
            "INSERT INTO questions (id, section_id, text, sort_order, created_at,"
            " updated_at) VALUES ("
            + sql_uuid(pk)
            + ", "
            + sql_uuid(section_pk)
            + ", "
            + sql_str(text)
            + ", "
            + str(as_int(number))
            + ", now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["questions"] += 1

    # --- model answers, stored as each question's answer template ---
    for answer_id, question_id, _topic_id, answer in answer_rows:
        pk = question_ids.get(str(question_id).strip())
        if pk is None or not answer:
            continue
        statements.append(
            "INSERT INTO answer_templates (id, question_id, template, sort_order,"
            " created_at, updated_at) VALUES ("
            + sql_uuid(det_id("answer", answer_id))
            + ", "
            + sql_uuid(pk)
            + ", "
            + sql_str(answer)
            + ", 0, now(), now()) ON CONFLICT (id) DO NOTHING;"
        )
        counts["answer_templates"] += 1

    statements.append("COMMIT;")
    return statements, dict(counts), slugs


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the topic workbook to SQL.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="write SQL here instead of stdout")
    args = parser.parse_args()

    statements, counts, slugs = build_sql(args.workbook)
    sql = "\n".join(statements) + "\n"

    if args.output:
        args.output.write_text(sql, encoding="utf-8")
    else:
        sys.stdout.write(sql)

    for table, count in sorted(counts.items()):
        print(f"{table:18} {count:5}", file=sys.stderr)

    duplicates = {slug for slug in slugs if slugs.count(slug) > 1}
    if duplicates:
        # topics.slug is UNIQUE, so a repeat would abort the transaction.
        print(f"WARNING duplicate topic slugs: {sorted(duplicates)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
