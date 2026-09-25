// Mirrors backend/app/schemas. Hand-written for Phase 1; generate from /openapi.json once
// the API surface settles (openapi-typescript).

export type SearchMode = "auto" | "vector" | "lexical" | "hybrid" | "rerank";
export type DocKind = "code" | "markdown" | "pdf" | "text";

export interface SearchFilters {
  source_ids?: number[] | null;
  doc_kinds?: DocKind[] | null;
  languages?: string[] | null;
  chunk_kinds?: string[] | null;
  path_prefix?: string | null;
  modified_after?: string | null;
  modified_before?: string | null;
}

export interface SearchHit {
  chunk_id: number;
  document_id: number;
  source_id: number;
  source_name: string;
  path: string;
  doc_kind: DocKind;
  language: string | null;
  title: string | null;
  chunk_kind: string;
  symbol: string | null;
  symbols: string[];
  start_line: number | null;
  end_line: number | null;
  header: string;
  content: string;
  modified_at: string | null;
  git_commit: string | null;
  meta: Record<string, unknown>;
  score: number;
  rerank_score: number | null;
  ranks: Record<string, number>;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  hits: SearchHit[];
  candidates: number;
  degraded: string[];
  timings_ms: Record<string, number>;
}

export interface RunStats {
  files_total?: number;
  files_done?: number;
  indexed?: number;
  unchanged?: number;
  failed?: number;
  needs_ocr?: number;
  deleted?: number;
  chunks_written?: number;
  embedded?: number;
  embed_pending?: number;
  skipped?: Record<string, number>;
  warnings?: string[];
}

export interface Run {
  id: number;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string | null;
  stats: RunStats;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Source {
  id: number;
  name: string;
  kind: "local" | "git";
  uri: string;
  status: "idle" | "queued" | "indexing" | "ready" | "failed";
  error: string | null;
  last_commit: string | null;
  last_indexed_at: string | null;
  created_at: string;
  documents: number;
  chunks: number;
  embedded: number;
  documents_by_kind: Record<string, number>;
  latest_run: Run | null;
}

export interface Stats {
  sources: number;
  documents: number;
  chunks: number;
  embedded: number;
  documents_by_kind: Record<string, number>;
  documents_by_language: Record<string, number>;
  chunks_by_kind: Record<string, number>;
  needs_ocr: number;
  failed: number;
}

export interface Chunk {
  id: number;
  ordinal: number;
  kind: string;
  symbol: string | null;
  symbols: string[];
  header: string;
  content: string;
  start_line: number | null;
  end_line: number | null;
  token_count: number;
  embedded: boolean;
  meta: Record<string, unknown>;
}

export interface DocumentDetail {
  id: number;
  source_id: number;
  source_name: string;
  path: string;
  kind: DocKind;
  language: string | null;
  title: string | null;
  size_bytes: number;
  status: string;
  error: string | null;
  modified_at: string | null;
  git_commit: string | null;
  git_author: string | null;
  meta: Record<string, unknown>;
  chunks: Chunk[];
}

export interface Health {
  status: "ok" | "degraded";
  checks: {
    models?: { ok: boolean; embedder: string; reranker: string; embedding_model?: string; error?: string };
    [key: string]: unknown;
  };
}
