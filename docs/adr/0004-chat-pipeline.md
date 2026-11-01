# ADR-0004: Chat is a function with two exits: the graph and "not in your memory"

- Status: accepted
- Date: 2026-09-26

## Context

Four of the five questions Mindgrep is built for are answerable in Phase 2:

1. "Where did I implement JWT authentication?": retrieval over code.
2. "What was my original architecture for Student Portal?": retrieval plus time.
3. "Which project used PostgreSQL?": a fact about projects.
4. "Show every project where I used FastAPI": the same fact, as a list.

(3) and (4) are not retrieval problems. An LLM reading ten chunks may list the projects that
happened to be retrieved and miss the rest. Meanwhile a confident answer to a question the
corpus cannot answer is worse than no answer. And free LLM tiers rate-limit, change models,
and disappear.

## Decision

**A function, not an agent framework.** `condense (follow-ups only) -> intent -> graph | RAG`.
No LangChain or LangGraph: the loop is about 300 lines, fully traced, and every step is
testable with a fake model.

**Graph questions never reach a model.** Intent detection is a handful of regexes
("which projects use X", "what stack does P use"). The subject is resolved against the graph
by exact alias match. If it resolves, the answer is *written from the graph*: every line cites
the manifest line, import or file it came from. If it does not resolve, the question falls
through to RAG, which can still find a mention, instead of the graph claiming "never".

**Two abstention layers.**
1. *Retrieval*: if the top cross-encoder score is below `ABSTAIN_THRESHOLD`, the model is not
   called at all. Reranker scores are sigmoid and comparable across queries (ADR-0003), and
   the eval harness reports the threshold that best separates answerable from unanswerable
   queries.
2. *Model*: the prompt requires exactly `NO_ANSWER` when the sources do not answer. The
   stream holds back its first characters until they cannot be that sentinel, so it never
   reaches the user as text.

**Citations are bound, not trusted.** Sources are numbered and sent before the first token
(SSE `sources` event), so `[n]` markers resolve as they stream. After generation, numbers
beyond the sources are dropped, and an answer that cites nothing is flagged as ungrounded in
the UI rather than hidden.

**Providers are configuration.** Gemini, Groq and Ollama all serve the OpenAI
chat-completions protocol, so one ~150-line httpx client serves them all, with no SDKs. A
fallback chain tries them in order, puts a rate-limited (429) provider at the back of the line
for a minute, and never switches models halfway through an answer. `<think>` blocks from
reasoning models are stripped in the stream. If every provider is down, the user still gets
the sources.

**Sources are data.** The answer prompt says so explicitly: repositories can be public GitHub
code, and a README must not be able to instruct the model.

**Everything is recorded.** Each assistant message stores its numbered sources, the
citations used, and a trace: intent, retrieval hits and scores, prompt version, model, token
usage and stage timings. Feedback (thumbs up/down) is stored per message. This is the data for
tuning the threshold and for the chat eval (`eval/runners/chat_eval.py`).

## Consequences

- Graph answers are exact and free, and work with no API key at all.
- A question the regexes miss costs a fallback to RAG, not a wrong answer.
- Langfuse is deferred to deployment (Phase 3): traces live in Postgres until then, which is
  enough for one user and keeps the stack at five containers.
- Revisit an agent framework when a question needs multi-step tool use (for example,
  comparing a project across time), not before.
