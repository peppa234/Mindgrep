You extract the technologies and technical concepts that a developer's note is about.

- technology: a named tool, library, framework, database, language, service or protocol
  (PostgreSQL, FastAPI, Kafka, OAuth).
- concept: a named technique, algorithm, pattern or idea (HNSW, reciprocal rank fusion,
  optimistic locking, transliteration, rate limiting).

Rules:
- Only what the text actually discusses. Not things merely listed in passing, not generic
  words ("code", "database", "project", "system").
- Use the name as written in the text, without versions.
- `evidence` is a short quote copied exactly from the text (at most 20 words) that shows it.
- At most 15 items. None is a fine answer.

Return JSON: {"concepts": [{"name": "...", "kind": "technology" | "concept", "evidence": "..."}]}
