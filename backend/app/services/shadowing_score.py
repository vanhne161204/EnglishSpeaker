"""Word-match scoring for Shadowing (PRD §8.14, Phase 1).

This compares the WORDS the learner said with the sentence. It is not a
pronunciation score and must never be shown as one (docs/10_AI_Design.md
§10.3.11): speech-to-text guesses words from context, so a badly pronounced word
can still come back right. Real pronunciation scoring is Phase 2.

How it works:

1. Both sides are normalised the same way: lower case, punctuation dropped,
   contractions expanded ("I'm" -> "i am"), small numbers spelled out ("5" -> "five").
2. An edit-distance alignment pairs each sentence word with what was heard.
   A near-miss in spelling ("colour"/"color") counts as ``close``.
3. Results are folded back onto the words as written, so "I'm" stays one word
   on screen even though it was matched as "i am".
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

Status = Literal["ok", "close", "wrong", "missed"]

#: Heard words beyond this are ignored: nobody shadows a 25-word sentence with 200.
MAX_HEARD_TOKENS = 200
#: Two words at least this long and this similar count as "close", not wrong.
CLOSE_MIN_LENGTH = 4
CLOSE_RATIO = 0.8
#: Speech time over model-voice time: above SLOW is too slow, below FAST too fast.
SLOW_RATIO = 1.35
FAST_RATIO = 0.75

_CONTRACTIONS: dict[str, str] = {
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "what's": "what is",
    "where's": "where is",
    "who's": "who is",
    "how's": "how is",
    "let's": "let us",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'd": "i would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
    "it'll": "it will",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "won't": "will not",
    "wouldn't": "would not",
    "can't": "can not",
    "cannot": "can not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "mustn't": "must not",
    "gonna": "going to",
    "wanna": "want to",
}

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen",
]
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy",
         8: "eighty", 9: "ninety"}

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)*")
_SPLIT = re.compile(r"[\s\-/–—]+")


#: Grammar endings Vietnamese speakers often drop (no Vietnamese word ends in a
#: consonant cluster), longest first, with the ending shown to the learner.
_ENDINGS: tuple[tuple[str, str], ...] = (
    ("'s", "-'s"),
    ("ing", "-ing"),
    ("ies", "-s"),
    ("ied", "-ed"),
    ("es", "-s"),
    ("ed", "-ed"),
    ("s", "-s"),
    ("d", "-ed"),
)
#: A bare word shorter than this is another word, not a dropped ending: "his" is
#: not "hi" + s.
MIN_BARE_LENGTH = 3


@dataclass(frozen=True, slots=True)
class WordScore:
    word: str
    heard: str | None
    status: Status
    #: The ending the learner left off ("-s", "-ed", "-ing", "-'s"); see ``ending_hint``.
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: int
    words: list[WordScore]
    extra: list[str]

    @property
    def words_ok(self) -> int:
        return sum(1 for word in self.words if word.status == "ok")


def _spell_number(token: str) -> list[str]:
    if not token.isdigit():
        return [token]
    number = int(token)
    if number < 20:
        return [_ONES[number]]
    if number < 100:
        tens, ones = divmod(number, 10)
        return [_TENS[tens]] + ([_ONES[ones]] if ones else [])
    return [token]


def tokenize(text: str) -> tuple[list[str], list[tuple[str, int]]]:
    """Split text into display words, and normalised tokens tagged with their word.

    Returns ``(words, tokens)`` where each token is ``(normalised, index into words)``.
    """
    words: list[str] = []
    tokens: list[tuple[str, int]] = []
    cleaned = text.replace("’", "'").replace("‘", "'")
    for chunk in _SPLIT.split(cleaned):
        found = _WORD.findall(chunk.lower())
        if not found:
            continue
        owner = len(words)
        words.append(chunk.strip(".,!?;:\"'()[]{}…"))
        for raw in found:
            for part in _CONTRACTIONS.get(raw, raw).split():
                for spelled in _spell_number(part):
                    tokens.append((spelled, owner))
    return words, tokens


def _similar(a: str, b: str) -> bool:
    if min(len(a), len(b)) < CLOSE_MIN_LENGTH:
        return False
    return SequenceMatcher(None, a, b).ratio() >= CLOSE_RATIO


def _sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return 0.5 if _similar(a, b) else 1.0


def align(ref: list[str], heard: list[str]) -> list[tuple[str, int | None, int | None]]:
    """Edit-distance alignment of two token lists.

    Returns ops in order: ``(status, ref_index, heard_index)`` where status is
    ``ok``/``close``/``wrong`` (paired), ``missed`` (a sentence token nobody said)
    or ``extra`` (a heard token that is not in the sentence).
    """
    n, m = len(ref), len(heard)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j - 1] + _sub_cost(ref[i - 1], heard[j - 1]),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )

    ops: list[tuple[str, int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            sub = _sub_cost(ref[i - 1], heard[j - 1])
            if cost[i][j] == cost[i - 1][j - 1] + sub:
                status = "ok" if sub == 0 else "close" if sub == 0.5 else "wrong"
                ops.append((status, i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            ops.append(("missed", i - 1, None))
            i -= 1
            continue
        ops.append(("extra", None, j - 1))
        j -= 1
    ops.reverse()
    return ops


def _bare_forms(word: str, suffix: str) -> set[str]:
    """The word with ``suffix`` taken off, allowing for English spelling:
    studies -> study, making -> make, stopped -> stop."""
    stem = word[: -len(suffix)]
    if suffix in ("ies", "ied"):
        return {stem + "y"}
    forms = {stem}
    if suffix in ("ing", "ed"):
        forms.add(stem + "e")
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            forms.add(stem[:-1])
    return forms


def ending_hint(expected: str, heard: str | None) -> str | None:
    """The ending the learner left off, when they said the bare word.

    "worked" heard as "work" gives "-ed"; "cats" heard as "cat" gives "-s". None
    when the words differ in any other way. Spelling only: no dictionary, no AI.
    """
    if not heard:
        return None
    word = expected.lower().replace("’", "'")
    said = heard.lower().replace("’", "'")
    if " " in said or word == said or len(said) < MIN_BARE_LENGTH:
        return None
    for suffix, shown in _ENDINGS:
        if word.endswith(suffix) and said in _bare_forms(word, suffix):
            return shown
    return None


def _merge(statuses: list[Status]) -> Status:
    """One status for a written word that was matched as several tokens ("I'm")."""
    if all(status == "ok" for status in statuses):
        return "ok"
    if all(status == "missed" for status in statuses):
        return "missed"
    if all(status in ("ok", "close") for status in statuses):
        return "close"
    return "wrong"


def score_words(reference: str, heard: str) -> MatchResult:
    """Word match between the sentence and what the learner was heard saying."""
    words, ref_tokens = tokenize(reference)
    _, heard_pairs = tokenize(heard)
    heard_tokens = [token for token, _ in heard_pairs][:MAX_HEARD_TOKENS]

    statuses: dict[int, list[Status]] = defaultdict(list)
    heard_for: dict[int, list[str]] = defaultdict(list)
    extra: list[str] = []
    for status, i, j in align([token for token, _ in ref_tokens], heard_tokens):
        if i is None:
            if j is not None:
                extra.append(heard_tokens[j])
            continue
        owner = ref_tokens[i][1]
        statuses[owner].append(status)  # type: ignore[arg-type]
        if j is not None:
            heard_for[owner].append(heard_tokens[j])

    results: list[WordScore] = []
    points = 0.0
    for index, word in enumerate(words):
        status = _merge(statuses.get(index) or ["missed"])
        points += 1.0 if status == "ok" else 0.5 if status == "close" else 0.0
        heard_word = " ".join(heard_for[index]) or None
        hint = ending_hint(word, heard_word) if status in ("close", "wrong") else None
        results.append(WordScore(word, heard_word, status, hint))

    score = round(100 * points / len(words)) if words else 0
    return MatchResult(score=score, words=results, extra=extra)


def tempo(
    duration_ms: int | None, reference_ms: int | None
) -> tuple[float | None, Literal["slow", "good", "fast"] | None]:
    """How the learner's speech time compares with the model voice."""
    if not duration_ms or not reference_ms:
        return None, None
    ratio = round(duration_ms / reference_ms, 2)
    if ratio > SLOW_RATIO:
        return ratio, "slow"
    if ratio < FAST_RATIO:
        return ratio, "fast"
    return ratio, "good"
