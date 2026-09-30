"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CodeBlock } from "@/components/code-block";
import { GlassPanel } from "@/components/visual/glass-panel";
import { api } from "@/lib/api";
import { lineRange, pageRange, relativeTime } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";

/** A file as the index sees it: every chunk, in order, with its boundaries and header. */
export function DocumentView({ id }: { id: number }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<string>("");

  useEffect(() => {
    api.document(id).then(setDoc).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (!doc) return;
    const hash = window.location.hash.slice(1);
    setTarget(hash);
    if (hash) document.getElementById(hash)?.scrollIntoView({ block: "start" });
  }, [doc]);

  if (error)
    return (
      <p className="alert" role="alert">
        {error}
      </p>
    );
  if (!doc) return <p className="text-sm text-mid">Loading…</p>;

  const tags = (doc.meta.tags as string[] | undefined) ?? [];
  const links = (doc.meta.links as string[] | undefined) ?? [];
  const imports = (doc.meta.imports as string[] | undefined) ?? [];
  const highlightAs = doc.kind === "code" ? doc.language : doc.kind === "markdown" ? "markdown" : null;

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <Link href="/search" className="text-sm text-mid hover:text-hi">
          ← Search
        </Link>
        <h1 className="font-mono text-lg font-normal tracking-normal break-all text-hi sm:text-xl">
          <span className="text-mid">{doc.source_name}/</span>
          {doc.path}
        </h1>
        {doc.title && doc.kind !== "code" && <p className="text-h3 font-display text-hi">{doc.title}</p>}
        <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-mid">
          <span>{doc.language ?? doc.kind}</span>
          <span>{(doc.size_bytes / 1024).toFixed(1)} KB</span>
          <span>{doc.chunks.length} chunks</span>
          {doc.modified_at && <span>modified {relativeTime(doc.modified_at)}</span>}
          {doc.git_commit && (
            <span>
              @{doc.git_commit.slice(0, 7)} {doc.git_author && `by ${doc.git_author}`}
            </span>
          )}
          {doc.status !== "indexed" && (
            <span className="flex items-center gap-1.5 text-hi">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />
              {doc.status}
            </span>
          )}
        </p>
        {(tags.length > 0 || links.length > 0) && (
          <p className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <span key={t} className="chip">
                #{t}
              </span>
            ))}
            {links.map((l) => (
              <span key={l} className="chip border-violet-400/40 text-violet-300">
                [[{l}]]
              </span>
            ))}
          </p>
        )}
        {imports.length > 0 && (
          <details className="text-xs text-mid">
            <summary className="cursor-pointer rounded-sm hover:text-hi">{imports.length} imports</summary>
            <pre className="code-surface mt-2 overflow-x-auto p-3 font-mono">{imports.join("\n")}</pre>
          </details>
        )}
      </div>

      {doc.status === "needs_ocr" && (
        <p className="alert">This PDF has no text layer (it looks scanned), so nothing from it is searchable yet. OCR support is planned.</p>
      )}

      <ol className="space-y-5">
        {doc.chunks.map((chunk) => {
          const anchor = `chunk-${chunk.id}`;
          const location = doc.kind === "pdf" ? pageRange(chunk.meta) : lineRange(chunk.start_line, chunk.end_line);
          const targeted = target === anchor;
          return (
            <li key={chunk.id} id={anchor} className="scroll-mt-24">
              <GlassPanel
                glow={false}
                padding="sm"
                tone={targeted ? "live" : "neutral"}
                className={`space-y-2 ${targeted ? "border-cyan-400/50 shadow-glow-cyan" : ""}`}
                aria-current={targeted ? "location" : undefined}
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-mid">
                  <span className="font-mono text-hi">#{chunk.ordinal}</span>
                  <span>{chunk.kind.replace("_", " ")}</span>
                  {chunk.symbol && <span className="font-mono text-hi">{chunk.symbol}</span>}
                  <span className="font-mono">{location}</span>
                  <span>~{chunk.token_count} tokens</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${chunk.embedded ? "bg-knowledge" : "border border-mid"}`} />
                    {chunk.embedded ? "embedded" : "not embedded yet"}
                  </span>
                </div>
                <details className="text-xs">
                  <summary className="cursor-pointer rounded-sm text-mid hover:text-hi">header (prepended when embedding)</summary>
                  <pre className="mt-1.5 font-mono whitespace-pre-wrap text-mid">{chunk.header}</pre>
                </details>
                <CodeBlock
                  content={chunk.content}
                  language={highlightAs}
                  startLine={doc.kind === "code" || doc.kind === "text" ? chunk.start_line : null}
                />
              </GlassPanel>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
