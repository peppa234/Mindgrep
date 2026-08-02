-- Runs once, on first boot of an empty data volume.
-- vector  : embedding storage + HNSW index (Phase 2)
-- pg_trgm : trigram similarity, for matching identifiers and entity aliases (Phase 4, Phase 6)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
