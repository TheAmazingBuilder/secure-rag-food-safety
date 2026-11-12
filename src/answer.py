"""Grounded, extractive answering — with citations, or a refusal.

Default behaviour needs no language model at all: the answer is built
from the kept (trusted, defended) passages and every claim is tied to a
citation ``[doc_id]``. If there is no trusted evidence, the system says
so instead of guessing. That refusal is a feature, and it is measured
in the evaluation.

A generative LLM is a *pluggable* option only: implement the
:class:`LLM` protocol and pass it in. :class:`OpenAILLM` activates only
when ``OPENAI_API_KEY`` is set in the environment, and it is never
required. Even with an LLM, the prompt is restricted to the kept
evidence — the model is instructed to answer only from that evidence
and to say it does not know otherwise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from .defense import DefenseResult

MIN_SCORE = 0.05  # below this, retrieval is treated as "no evidence"

# Words too generic to count as evidence that a passage answers a question.
_GENERIC_WORDS = {
    "what", "which", "when", "where", "how", "long", "does", "should",
    "would", "could", "there", "about", "temperature", "temperatures",
    "safe", "safety", "food", "cooking", "cook", "cooked", "reach",
    "reach", "keep", "kept", "set", "eat", "canada", "canadian", "meat",
}


def _has_evidence_overlap(question: str, kept: list) -> bool:
    """True if a distinctive word from the question appears in the evidence.

    This is what stops a plausible-looking but unrelated answer: a
    question about kangaroo retrieves generic cooking-temperature
    passages, but none of them mentions kangaroo, so there is no
    evidence — even though the retrieval scores look fine. If the
    question has no distinctive word at all, fall back to True.
    """
    words = {
        w.strip("?.!,").lower()
        for w in question.split()
        if len(w.strip("?.!,")) > 3
    }
    distinctive = words - _GENERIC_WORDS
    if not distinctive:
        return True
    evidence = " ".join(s.chunk.text.lower() for s in kept)
    return any(word in evidence for word in distinctive)


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)
    refused: bool = False
    flags: list[str] = field(default_factory=list)


class LLM(Protocol):
    def generate(self, prompt: str) -> str: ...


class OpenAILLM:
    """Optional LLM, only when OPENAI_API_KEY is set. Never required."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content or ""


def _extractive_answer(question: str, defense: DefenseResult) -> Answer:
    kept = [s for s in defense.kept if s.score >= MIN_SCORE]
    if not kept or not _has_evidence_overlap(question, kept):
        return Answer(
            text=(
                "I don't have trusted evidence in the corpus to answer "
                "that question. I won't guess — please check the source "
                "guidance directly."
            ),
            citations=[],
            refused=True,
            flags=list(defense.flags),
        )
    parts: list[str] = []
    citations: list[str] = []
    for scored in kept:
        chunk = scored.chunk
        parts.append(f"{chunk.text} [{chunk.doc_id}]")
        if chunk.doc_id not in citations:
            citations.append(chunk.doc_id)
    text = "Based on the retrieved guidance:\n\n" + "\n\n".join(parts)
    if any("Conflicting" in f for f in defense.flags):
        text += (
            "\n\nNote: the retrieved passages disagree on a temperature. "
            "Treat the answer above as conflicting evidence and check "
            "the cited sources before acting on it."
        )
    return Answer(text=text, citations=citations, refused=False, flags=list(defense.flags))


def generate_answer(
    question: str, defense: DefenseResult, llm: LLM | None = None
) -> Answer:
    """Answer from defended evidence; optionally via an LLM, same rules."""
    if llm is None:
        return _extractive_answer(question, defense)
    kept = [s for s in defense.kept if s.score >= MIN_SCORE]
    if not kept or not _has_evidence_overlap(question, kept):
        return _extractive_answer(question, defense)
    evidence = "\n\n".join(
        f"[{s.chunk.doc_id}] {s.chunk.text}" for s in kept
    )
    prompt = (
        "Answer the question using ONLY the evidence below. "
        "Cite each claim with its [doc_id]. If the evidence does not "
        "answer the question, say you do not have trusted evidence.\n\n"
        f"Evidence:\n{evidence}\n\nQuestion: {question}"
    )
    text = llm.generate(prompt)
    citations = [s.chunk.doc_id for s in kept]
    return Answer(text=text, citations=citations, refused=False, flags=list(defense.flags))
