# secure-rag-food-safety

A small, complete, honest RAG project — with a security experiment built in.

It answers food-safety questions from a small trusted corpus of Canadian
guidance (Health Canada / CFIA), cites its sources, refuses when it has
no trusted evidence, and is tested against two attacks: **prompt
injection** and **knowledge poisoning**.

## Why this exists

I built this to prepare for the CIS*6560 Winter 2027 research internship
at the University of Guelph — *"Security Evaluation and Resilience of
RAG-LLMs for Food-Safety Applications"* (Cyber Science Lab, supervisors
Fattane Zarrinkalam and Ali Dehghantanha).

It is a learning project, not a production system and not a finished
RAG product. Its job is to show, in runnable code, the exact skills
that internship asks for: build a small RAG baseline, define a threat
model, create controlled attack cases, implement one defence, and
measure clean vs. attacked vs. defended on the same questions.

## How it works, in plain words

1. **Ingest** (`src/ingest.py`) — loads 7 short Markdown documents from
   `data/corpus/`, each with title, source URL, and access date, and
   splits them into overlapping chunks.
2. **Retrieve** (`src/retrieve.py`) — TF-IDF + cosine similarity by
   default. Offline, deterministic, no API key, no download. A dense
   embedder (`SentenceTransformerEmbedder`) is available as an opt-in,
   behind a clean `Embedder` interface — it is never required.
3. **Defend** (`src/defense.py`) — the one defence in this project:
   source validation (only trusted corpus sources may be cited) +
   instruction detection (passages telling the model what to say are
   dropped) + an evidence-consistency check (conflicting temperatures
   for the same food are flagged).
4. **Answer** (`src/answer.py`) — extractive by default: the answer is
   built from the kept passages, each claim cited as `[doc_id]`. If
   there is no trusted evidence, it refuses instead of guessing.
   A generative LLM is pluggable (`LLM` protocol); `OpenAILLM` only
   activates if `OPENAI_API_KEY` is set. It is never required.
5. **Evaluate** (`src/evaluate.py`) — runs 12 cases (8 benign,
   1 no-evidence, 1 injection, 2 poisoning) and reports retrieval hit
   rate, citation presence / integrity, attack success rate, and
   refusal behaviour — for the defended run and the undefended baseline.

## The corpus

`data/corpus/` — 7 short documents, all labelled **Summary** (paraphrased
from the source, not verbatim quotes), each with a verified source URL:

| Doc | Topic | Source |
| --- | --- | --- |
| 01 | Clean, Separate, Cook, Chill | Health Canada / Healthy Canadians |
| 02 | Safe internal cooking temperatures | Health Canada cooking-temperatures chart |
| 03 | Safe storage & the danger zone (4–60 °C) | Health Canada |
| 04 | Produce safety | Canada.ca / Health Canada |
| 05 | Allergen labelling (priority allergens) | CFIA |
| 06 | Preventive control plans & HACCP | CFIA / FSEP |
| 07 | Recalls & when in doubt, throw it out | Health Canada |

`data/attacks/` — 3 **synthetic, clearly labelled** test passages
(`SYNTHETIC / TEST ONLY`): one prompt injection (raw chicken), two
knowledge-poisoning passages (ground beef at 40 °C, fridge at 15 °C).
They are never mixed silently into the trusted corpus; they are loaded
only with `--include-attacks` or by the evaluation harness.

See `docs/threat-model.md` for the full threat model, including what
is out of scope and what the defence does *not* protect against.

## Setup — 5 minutes

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+ required. No API key needed.

## Run it

```bash
# See the corpus
python -m src.main ingest

# Ask a question (trusted corpus only)
python -m src.main ask "What temperature should ground beef reach?"

# Ask with the synthetic attacks loaded (test only — flagged loudly)
python -m src.main ask "Is raw chicken safe to eat?" --include-attacks

# Run the evaluation: defended, undefended, and both for comparison
python -m src.main evaluate
python -m src.main evaluate --undefended
python -m src.main evaluate --both
```

## Example

```
$ python -m src.main ask "What temperature should ground beef reach?"
Retrieved:
  - 02-safe-cooking-temperatures-0 (score=0.312)

Based on the retrieved guidance:

Ground beef, veal, lamb, and pork should reach 71 degrees Celsius
(160 degrees Fahrenheit). [02-safe-cooking-temperatures]

Citations: 02-safe-cooking-temperatures
```

And with the defence, an injection attempt is dropped before answering:

```
$ python -m src.main ask "Is raw chicken safe to eat?" --include-attacks
WARNING: synthetic attack passages are loaded for testing only.

FLAG: Dropped attack-01-injection-chicken-0: source
'attack-01-injection-chicken' is not in the trusted corpus.

Based on the retrieved guidance:
Poultry pieces should reach 74 degrees Celsius ... [02-safe-cooking-temperatures]
```

## Tests

```bash
python -m pytest -q
```

13 tests: chunking, corpus loading, retrieval relevance and
determinism, citations, refusal, injection flagging, poisoned passages
never cited as trusted, consistency checks, and a defended-vs-undefended
evaluation comparison.

## Evaluation — sample results

See `examples/evaluation-results.md` for a captured run. In short,
on 12 cases: defended — attack success rate 0.00, citation integrity
1.00, retrieval hit rate 0.83; undefended baseline — attack success
rate 1.00, citation integrity 0.33. Benign retrieval is unchanged
(0.88 hit rate in both runs) — the defence is not supposed to make
good answers worse, and the evaluation checks that. One honest miss:
case B04 (danger zone) scores hit=False because the expected document
is not in the top 3, although the answer itself is correct — another
document also states the danger zone.

## Limitations — read this before judging the project

- **Tiny corpus, tiny evaluation.** 7 documents, 12 test cases. This
  proves the pipeline works and the defence is measurable; it proves
  nothing about a real, large RAG system.
- **TF-IDF is lexical.** A well-worded false passage can outrank a
  true one. That is part of what the experiment measures.
- **The defence is one control, not security.** Source validation is
  what stops a poisoned passage here. If an attacker can write into
  the trusted corpus itself, this defence does not help — see the
  threat model.
- **No-evidence handling is a simple heuristic.** The refusal check
  (`_has_evidence_overlap` in `src/answer.py`) refuses when no
  distinctive word from the question appears in the kept evidence —
  it correctly refuses the kangaroo case in the evaluation — but a
  question worded with only generic terms could still slip through.
  The evaluation reports when it fails.
- **Summaries, not quotes.** Corpus passages are paraphrases of public
  guidance, clearly labelled as such. For real compliance decisions,
  always read the source itself. This project gives no food-safety
  advice for production use.

## How this maps to the internship deliverables

| Internship deliverable | Here |
| --- | --- |
| Reproducible RAG baseline + curated public corpus | `src/` + `data/corpus/`, `python -m src.main ingest` |
| Documented threat model + controlled evaluation set | `docs/threat-model.md` + `data/eval/questions.json` (12 cases) |
| Sandboxed attack-testing harness with logs | `--include-attacks`, `src/evaluate.py`, flags printed per case |
| One working defence + baseline/attacked/defended comparison | `src/defense.py`, `python -m src.main evaluate --both` |
| Repository with tests and documentation | `tests/`, this README, `examples/evaluation-results.md` |

## Author

Rody G. Bints — AI Engineer / Software Developer.
GitHub: https://github.com/TheAmazingBuilder ·
LinkedIn: https://www.linkedin.com/in/rody-bints
