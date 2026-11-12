"""The defence: source validation + evidence-consistency checks.

This is the one defence implemented in this project, on purpose. It is
small, explainable, and testable:

1. **Source validation** — only chunks whose ``doc_id`` is in the trusted
   corpus may be cited. Anything else (for example a synthetic attack
   passage loaded by mistake) is dropped before answering.
2. **Instruction detection** — a retrieved passage that contains an
   instruction aimed at the model ("ignore previous instructions",
   "disregard the above", "you must say ...") is flagged and excluded
   from the evidence used to answer.
3. **Consistency check** — when two trusted passages give different
   numbers for the same food/temperature pair (e.g. two different safe
   temperatures for ground beef), the answer is flagged as conflicting
   instead of silently picking one.

None of this makes a system "secure" in general. It is one measurable
control, compared against the undefended baseline in ``src/evaluate.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ingest import Chunk
from .retrieve import ScoredChunk

INSTRUCTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (the )?(above|previous|prior)",
    r"override (the )?(above|previous|prior|system)",
    r"you must (say|answer|respond|tell|claim)",
    r"do not (mention|follow|use|trust) (the )?(above|previous|prior|other)",
    r"forget (everything|the above|your instructions)",
    r"new instruction",
    r"system prompt",
]

_TEMP_RE = re.compile(r"(\d{2,3})\s*(?:°\s*C|degrees\s+Celsius)", re.IGNORECASE)
_FOOD_WORDS = [
    "ground beef", "ground poultry", "poultry", "chicken", "beef",
    "pork", "leftovers", "fish", "egg",
]


@dataclass
class DefenseResult:
    kept: list[ScoredChunk] = field(default_factory=list)
    dropped: list[ScoredChunk] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def contains_instruction(text: str) -> bool:
    """True if the text looks like an instruction aimed at the model."""
    lowered = text.lower()
    return any(re.search(p, lowered) for p in INSTRUCTION_PATTERNS)


def check_consistency(chunks: list[ScoredChunk]) -> list[str]:
    """Flag numeric disagreements on the same food across passages.

    Only unambiguous sentences count: a sentence with exactly one
    temperature and exactly one food phrase (longest match wins, so
    "ground beef" does not also count as "beef"). A temperature table
    or a sentence listing several temperatures for several cuts is
    not a conflict — it is just a table. A flag therefore means two
    different chunks each state a single, different temperature for
    the same food.
    """
    # food -> temp -> set of chunk ids stating it
    claims: dict[str, dict[str, set[str]]] = {}
    for scored in chunks:
        chunk = scored.chunk
        for sentence in re.split(r"(?<=[.!?])\s+", chunk.text):
            temps = _TEMP_RE.findall(sentence)
            if len(temps) != 1:
                continue
            lowered = sentence.lower()
            foods = [
                f for f in _FOOD_WORDS
                if re.search(rf"\b{re.escape(f)}\b", lowered)
            ]
            # Longest match wins: "ground beef" subsumes "beef".
            foods = [f for f in foods if not any(
                f != other and f in other for other in foods
            )]
            if len(foods) != 1:
                continue
            claims.setdefault(foods[0], {}).setdefault(temps[0], set()).add(chunk.chunk_id)
    flags: list[str] = []
    for food, by_temp in claims.items():
        if len(by_temp) > 1:
            temps = ", ".join(sorted(by_temp))
            flags.append(
                f"Conflicting temperatures for {food}: {temps} °C "
                "across retrieved passages."
            )
    return flags


def apply_defense(
    retrieved: list[ScoredChunk], trusted_doc_ids: set[str]
) -> DefenseResult:
    """Filter retrieved chunks to trusted, non-instructional evidence."""
    result = DefenseResult()
    for scored in retrieved:
        chunk = scored.chunk
        if chunk.doc_id not in trusted_doc_ids:
            result.dropped.append(scored)
            result.flags.append(
                f"Dropped {chunk.chunk_id}: source '{chunk.doc_id}' "
                "is not in the trusted corpus."
            )
            continue
        if contains_instruction(chunk.text):
            result.dropped.append(scored)
            result.flags.append(
                f"Dropped {chunk.chunk_id}: passage contains an "
                "instruction aimed at the model (possible prompt injection)."
            )
            continue
        result.kept.append(scored)
    result.flags.extend(check_consistency(result.kept))
    return result
