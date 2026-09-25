"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CodeBlock } from "@/components/code-block";
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

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!doc) return <p className="text-sm text-zinc-500">Loading…</p>;

  const tags = (doc.meta.tags as string[] | undefined) ?? [];
  const links = (doc.meta.links as string[] | undefined) ?? [];
  const imports = (doc.meta.imports as string[] | undefined) ?? [];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link href="/search" className="text-xs text-zinc-500 hover:underline">
          ← back to search
        </Link>
        <h1 className="font-mono text-lg break-all">
          <span className="text-zinc-400">{doc.source_name}/</span>
          {doc.path}
        </h1>
        {doc.title && doc.kind !== "code" && <p className="text-zinc-600 dark:text-zinc-400">{doc.title}</p>}
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>{doc.language ?? doc.kind}</span>
          <span>{(doc.size_bytes / 1024).toFixed(1)} KB</span>
          <span>{doc.chunks.length} chunks</span>
          {doc.modified_at && <span>modified {relativeTime(doc.modified_at)}</span>}
          {doc.git_commit && (
            <span className="font-mono">
              @{doc.git_commit.slice(0, 7)} {doc.git_author && `by ${doc.git_author}`}
            </span>
          )}
          {doc.status !== "indexed" && <span className="text-amber-600">{doc.status}</span>}
        </p>
        {(tags.length > 0 || links.length > 0) && (
          <p className="flex flex-wrap gap-1.5 text-xs">
            {tags.map((t) => (
              <span key={t} className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
                #{t}
              </span>
            ))}
            {links.map((l) => (
              <span key={l} className="rounded-full border border-zinc-200 px-2 py-0.5 dark:border-zinc-700">
                [[{l}]]
              </span>
            ))}
          </p>
        )}
        {imports.length > 0 && (
          <details className="text-xs text-zinc-500">
            <summary className="cursor-pointer">{imports.length} imports</summary>
            <pre className="mt-1 font-mono">{imports.join("\n")}</pre>
          </details>
        )}
      </div>

      {doc.status === "needs_ocr" && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          This PDF has no text layer (it looks scanned), so nothing from it is searchable yet. OCR support is planned.
        </p>
      )}

      <ol className="space-y-5">
        {doc.chunks.map((chunk) => {
          const anchor = `chunk-${chunk.id}`;
          const location = doc.kind === "pdf" ? pageRange(chunk.meta) : lineRange(chunk.start_line, chunk.end_line);
          return (
            <li
              key={chunk.id}
              id={anchor}
              className={`scroll-mt-20 space-y-1.5 rounded-lg p-2 ${target === anchor ? "bg-amber-50 ring-1 ring-amber-300 dark:bg-amber-500/5 dark:ring-amber-800" : ""}`}
            >
              <div className="flex flex-wrap items-baseline gap-2 text-xs text-zinc-500">
                <span className="font-mono">#{chunk.ordinal}</span>
                <span>{chunk.kind.replace("_", " ")}</span>
                {chunk.symbol && <span className="font-mono text-zinc-800 dark:text-zinc-200">{chunk.symbol}</span>}
                <span className="font-mono">{location}</span>
                <span>~{chunk.token_count} tokens</span>
                <span
                  className={`h-1.5 w-1.5 rounded-full ${chunk.embedded ? "bg-emerald-500" : "bg-zinc-300 dark:bg-zinc-700"}`}
                  title={chunk.embedded ? "embedded" : "not embedded yet"}
                />
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-zinc-400">header (prepended when embedding)</summary>
                <pre className="mt-1 whitespace-pre-wrap font-mono text-zinc-500">{chunk.header}</pre>
              </details>
              <CodeBlock
                content={chunk.content}
                startLine={doc.kind === "code" || doc.kind === "text" ? chunk.start_line : null}
              />
            </li>
          );
        })}
      </ol>
    </div>
  );
}
