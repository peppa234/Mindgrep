"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { CodeBlock } from "@/components/code-block";
import { GlassPanel } from "@/components/visual/glass-panel";
import { api } from "@/lib/api";
import { lineRange, pageRange, relativeTime } from "@/lib/format";
import { EASE_MEMORY, SPRING_LAYOUT, STAGGER } from "@/lib/motion";
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
    <GlassPanel as="article" padding="none" className="space-y-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-sm">
        <span className="chip py-0 font-mono text-[11px] uppercase">{hit.language ?? hit.doc_kind}</span>
        <Link href={`/documents/${hit.document_id}#chunk-${hit.chunk_id}`} className="link min-w-0 truncate font-mono text-[13px]">
          {hit.source_name}/{hit.path}
        </Link>
        {location && <span className="font-mono text-xs text-mid">{location}</span>}
        <span className="ml-auto text-xs text-mid" title={hit.git_commit ? `commit ${hit.git_commit}` : "file modified"}>
          {relativeTime(hit.modified_at)}
        </span>
      </div>
      {hit.symbol && hit.doc_kind !== "pdf" && (
        <h3 className="font-mono text-[15px] font-medium tracking-normal text-hi">
          {hit.symbol}
          <span className="ml-2 font-sans text-xs font-normal text-mid">{hit.chunk_kind.replace("_", " ")}</span>
        </h3>
      )}
      {hit.doc_kind === "pdf" && hit.title && <h3 className="text-h3">{hit.title}</h3>}
      <CodeBlock
        content={hit.content}
        language={hit.doc_kind === "code" ? hit.language : null}
        startLine={hit.doc_kind === "code" || hit.doc_kind === "text" ? hit.start_line : null}
        terms={terms(query)}
        maxLines={14}
      />
      <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-mid">
        {Object.entries(hit.ranks).map(([channel, rank]) => (
          <span key={channel} className="chip py-0 text-[11px]" title={`rank ${rank} in the ${channel} channel`}>
            {CHANNEL_LABEL[channel] ?? channel} #{rank}
          </span>
        ))}
        {hit.rerank_score != null && (
          <span className="chip py-0 text-[11px] text-hi" title="cross-encoder relevance, 0–1">
            rerank {hit.rerank_score.toFixed(3)}
          </span>
        )}
      </div>
    </GlassPanel>
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
      const typing =
        e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement;
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
  }, [params, mode, kinds, sourceId]); // eslint-disable-line react-hooks/exhaustive-deps

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
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="sr-only">Search</h1>
      <form onSubmit={submit} role="search" className="space-y-3">
        {/* The command bar: the glass lights up while the input has focus. */}
        <div className="glass flex items-center gap-3 px-4 transition-[border-color,box-shadow] duration-300 focus-within:border-line-bright focus-within:shadow-glow-violet has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-violet-400">
          <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-mid" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <circle cx="11" cy="11" r="7" />
            <path strokeLinecap="round" d="m20 20-3.5-3.5" />
          </svg>
          <label htmlFor="search-input" className="sr-only">
            Search your memory
          </label>
          <input
            id="search-input"
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what you're looking for: a function, a note, an idea…"
            className="h-14 min-w-0 flex-1 bg-transparent text-base text-hi outline-none placeholder:text-mid"
          />
          {loading ? (
            <span className="flex items-center gap-2 font-mono text-xs text-cyan-400" role="status">
              <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-live shadow-glow-cyan motion-off:animate-none" />
              searching
            </span>
          ) : (
            <span className="kbd hidden sm:inline" aria-hidden>
              Ctrl K
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div className="seg" role="group" aria-label="Search mode">
            {MODES.map((m) => (
              <button key={m.value} type="button" title={m.hint} aria-pressed={mode === m.value} onClick={() => setMode(m.value)}>
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex gap-1" role="group" aria-label="Document kinds">
            {KINDS.map((kind) => (
              <button key={kind} type="button" aria-pressed={kinds.includes(kind)} onClick={() => toggleKind(kind)} className="chip">
                {kind}
              </button>
            ))}
          </div>
          <select
            value={sourceId ?? ""}
            onChange={(e) => setSourceId(e.target.value ? Number(e.target.value) : null)}
            aria-label="Source"
            className="field h-8 rounded-lg px-2 text-xs"
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
            aria-label="Path prefix"
            placeholder="path prefix, e.g. src/"
            className="field h-8 w-44 rounded-lg px-2 font-mono text-xs"
          />
        </div>
      </form>

      {sources?.length === 0 && (
        <GlassPanel glow={false} className="text-center text-sm text-mid">
          Nothing indexed yet.{" "}
          <Link href="/sources" className="link">
            Add a folder or a GitHub repository
          </Link>{" "}
          to start.
        </GlassPanel>
      )}

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {result && result.degraded.length > 0 && <p className="notice">Partial results. {result.degraded.join(" · ")}</p>}

      {result && (
        <div className="flex items-center justify-between font-mono text-xs text-mid" aria-live="polite">
          <span>
            {result.hits.length} of {result.candidates} candidates · mode <span className="text-hi">{result.mode}</span>
          </span>
          <span title={Object.entries(result.timings_ms).map(([k, v]) => `${k}: ${v} ms`).join("\n")}>
            {result.timings_ms.total?.toFixed(0)} ms
          </span>
        </div>
      )}

      <motion.ul layout className={`space-y-4 transition-opacity duration-300 ${loading ? "opacity-60" : ""}`}>
        <AnimatePresence mode="popLayout" initial={false}>
          {result?.hits.map((hit, i) => (
            <motion.li
              key={hit.chunk_id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_MEMORY, delay: Math.min(i, 10) * STAGGER } }}
              exit={{ opacity: 0, transition: { duration: 0.15 } }}
              transition={SPRING_LAYOUT}
            >
              <Hit hit={hit} query={result.query} />
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
      {result && result.hits.length === 0 && <p className="py-12 text-center text-sm text-mid">No matches. Try describing it differently.</p>}

      {!result && !loading && sources && sources.length > 0 && (
        <div className="space-y-3 pt-8 text-center text-sm">
          <p className="text-mid">Try</p>
          <div className="flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  router.replace(`${pathname}?q=${encodeURIComponent(example)}`);
                }}
                className="chip font-mono"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
