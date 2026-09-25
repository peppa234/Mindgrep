"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { CodeBlock } from "@/components/code-block";
import { api } from "@/lib/api";
import { lineRange, pageRange, relativeTime } from "@/lib/format";
import type { DocKind, SearchHit, SearchMode, SearchResponse, Source } from "@/lib/types";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "auto", label: "Auto", hint: "Best available: hybrid + rerank" },
  { value: "rerank", label: "Rerank", hint: "Hybrid candidates reordered by a cross-encoder" },
  { value: "hybrid", label: "Hybrid", hint: "Vector + full-text + symbol names, fused with RRF" },
  { value: "vector", label: "Vector", hint: "Dense embeddings only" },
  { value: "lexical", label: "Lexical", hint: "Full-text and identifier matching only" },
];
const KINDS: DocKind[] = ["code", "markdown", "pdf", "text"];
const CHANNEL_LABEL: Record<string, string> = { vector: "vec", lexical: "fts", symbol: "sym" };
const EXAMPLES = [
  "where did I implement JWT authentication",
  "retry with exponential backoff",
  "notes about vector index parameters",
];

function terms(q: string): string[] {
  return q
    .split(/[^A-Za-z0-9_]+/)
    .flatMap((w) => [w, ...w.split(/_|(?=[A-Z][a-z])/)])
    .filter((w) => w.length >= 3);
}

function Hit({ hit, query }: { hit: SearchHit; query: string }) {
  const location = hit.doc_kind === "pdf" ? pageRange(hit.meta) : lineRange(hit.start_line, hit.end_line);
  return (
    <article className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
        <span className="rounded bg-zinc-200/70 px-1.5 py-0.5 font-mono text-[11px] uppercase text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          {hit.language ?? hit.doc_kind}
        </span>
        <Link
          href={`/documents/${hit.document_id}#chunk-${hit.chunk_id}`}
          className="font-mono text-[13px] text-zinc-600 hover:text-amber-700 hover:underline dark:text-zinc-400 dark:hover:text-amber-400"
        >
          {hit.source_name}/{hit.path}
        </Link>
        {location && <span className="font-mono text-xs text-zinc-400">{location}</span>}
        <span className="ml-auto text-xs text-zinc-400" title={hit.git_commit ? `commit ${hit.git_commit}` : "file modified"}>
          {relativeTime(hit.modified_at)}
        </span>
      </div>
      {hit.symbol && hit.doc_kind !== "pdf" && (
        <h3 className="font-mono text-[15px] font-medium">
          {hit.symbol}
          <span className="ml-2 font-sans text-xs font-normal text-zinc-400">{hit.chunk_kind.replace("_", " ")}</span>
        </h3>
      )}
      {hit.doc_kind === "pdf" && hit.title && <h3 className="text-[15px] font-medium">{hit.title}</h3>}
      <CodeBlock
        content={hit.content}
        startLine={hit.doc_kind === "code" || hit.doc_kind === "text" ? hit.start_line : null}
        terms={terms(query)}
        maxLines={14}
      />
      <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-zinc-500">
        {Object.entries(hit.ranks).map(([channel, rank]) => (
          <span
            key={channel}
            className="rounded border border-zinc-200 px-1.5 dark:border-zinc-800"
            title={`rank ${rank} in the ${channel} channel`}
          >
            {CHANNEL_LABEL[channel] ?? channel} #{rank}
          </span>
        ))}
        {hit.rerank_score != null && (
          <span className="rounded border border-amber-300 px-1.5 text-amber-700 dark:border-amber-800 dark:text-amber-400" title="cross-encoder relevance, 0–1">
            rerank {hit.rerank_score.toFixed(3)}
          </span>
        )}
      </div>
    </article>
  );
}

export function SearchView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState(params.get("q") ?? "");
  const [mode, setMode] = useState<SearchMode>((params.get("mode") as SearchMode) ?? "auto");
  const [kinds, setKinds] = useState<DocKind[]>((params.get("kinds")?.split(",").filter(Boolean) as DocKind[]) ?? []);
  const [sourceId, setSourceId] = useState<number | null>(params.get("source") ? Number(params.get("source")) : null);
  const [pathPrefix, setPathPrefix] = useState(params.get("path") ?? "");
  const [sources, setSources] = useState<Source[] | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.sources().then(setSources).catch(() => setSources([]));
  }, []);

  // "/" or Ctrl/Cmd+K focuses the search box from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = useCallback(
    async (q: string) => {
      if (!q.trim()) return;
      setLoading(true);
      setError(null);
      try {
        const filters = {
          doc_kinds: kinds.length ? kinds : null,
          source_ids: sourceId ? [sourceId] : null,
          path_prefix: pathPrefix.trim() || null,
        };
        setResult(await api.search(q, mode, filters));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [kinds, mode, pathPrefix, sourceId],
  );

  // Keep the URL shareable, and re-run when filters change.
  useEffect(() => {
    const q = params.get("q");
    if (q) run(q);
  }, [params, mode, kinds, sourceId]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const next = new URLSearchParams();
    if (query.trim()) next.set("q", query.trim());
    if (mode !== "auto") next.set("mode", mode);
    if (kinds.length) next.set("kinds", kinds.join(","));
    if (sourceId) next.set("source", String(sourceId));
    if (pathPrefix.trim()) next.set("path", pathPrefix.trim());
    router.replace(`${pathname}?${next.toString()}`);
    if (next.toString() === params.toString()) run(query);
  }

  const toggleKind = (kind: DocKind) =>
    setKinds((current) => (current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]));

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="space-y-3">
        <div className="relative">
          <input
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what you're looking for: a function, a note, an idea…"
            className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 pr-20 text-base shadow-sm outline-none placeholder:text-zinc-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <kbd className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded border border-zinc-200 px-1.5 font-mono text-[11px] text-zinc-400 dark:border-zinc-700">
            Ctrl K
          </kbd>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div className="flex rounded-md border border-zinc-200 p-0.5 dark:border-zinc-800">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                title={m.hint}
                onClick={() => setMode(m.value)}
                className={`rounded px-2.5 py-1 text-xs ${
                  mode === m.value
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            {KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => toggleKind(kind)}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${
                  kinds.includes(kind)
                    ? "border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
                    : "border-zinc-200 text-zinc-500 dark:border-zinc-800"
                }`}
              >
                {kind}
              </button>
            ))}
          </div>
          <select
            value={sourceId ?? ""}
            onChange={(e) => setSourceId(e.target.value ? Number(e.target.value) : null)}
            className="rounded-md border border-zinc-200 bg-transparent px-2 py-1 text-xs dark:border-zinc-800"
          >
            <option value="">All sources</option>
            {sources?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <input
            value={pathPrefix}
            onChange={(e) => setPathPrefix(e.target.value)}
            onBlur={() => submit()}
            placeholder="path prefix, e.g. src/"
            className="w-44 rounded-md border border-zinc-200 bg-transparent px-2 py-1 font-mono text-xs dark:border-zinc-800"
          />
        </div>
      </form>

      {sources?.length === 0 && (
        <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
          Nothing indexed yet.{" "}
          <Link href="/sources" className="text-amber-700 underline dark:text-amber-400">
            Add a folder or a GitHub repository
          </Link>{" "}
          to start.
        </p>
      )}

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>
      )}

      {result && result.degraded.length > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          Partial results. {result.degraded.join(" · ")}
        </p>
      )}

      {result && (
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>
            {result.hits.length} of {result.candidates} candidates · mode <b>{result.mode}</b>
          </span>
          <span title={Object.entries(result.timings_ms).map(([k, v]) => `${k}: ${v} ms`).join("\n")}>
            {result.timings_ms.total?.toFixed(0)} ms
          </span>
        </div>
      )}

      <div className={`space-y-8 transition-opacity ${loading ? "opacity-50" : ""}`}>
        {result?.hits.map((hit) => <Hit key={hit.chunk_id} hit={hit} query={result.query} />)}
        {result && result.hits.length === 0 && (
          <p className="py-12 text-center text-sm text-zinc-500">No matches. Try describing it differently.</p>
        )}
      </div>

      {!result && !loading && sources && sources.length > 0 && (
        <div className="space-y-2 pt-8 text-center text-sm text-zinc-500">
          <p>Try:</p>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => {
                setQuery(example);
                router.replace(`${pathname}?q=${encodeURIComponent(example)}`);
              }}
              className="block w-full font-mono text-xs hover:text-amber-700 dark:hover:text-amber-400"
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
