"use client";

import { Fragment, useMemo, useState } from "react";

function highlight(line: string, pattern: RegExp | null) {
  if (!pattern || !line) return line || " ";
  const parts = line.split(pattern);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded-sm bg-amber-200/80 text-inherit dark:bg-amber-400/25">
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** Source text with real line numbers (from the file, not from 1) and query terms marked. */
export function CodeBlock({
  content,
  startLine,
  terms = [],
  maxLines,
}: {
  content: string;
  startLine: number | null;
  terms?: string[];
  maxLines?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const lines = content.split("\n");
  const limit = maxLines && !expanded ? maxLines : lines.length;
  const pattern = useMemo(() => {
    const words = terms.filter((t) => t.length >= 3).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return words.length ? new RegExp(`(${words.join("|")})`, "gi") : null;
  }, [terms]);
  const first = startLine ?? 1;
  const width = String(first + lines.length).length;

  return (
    <div className="overflow-hidden rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/60">
      <pre className="overflow-x-auto py-2 font-mono text-[12.5px] leading-5">
        {lines.slice(0, limit).map((line, i) => (
          <div key={i} className="flex">
            {startLine != null && (
              <span
                className="sticky left-0 shrink-0 select-none bg-white pr-3 pl-3 text-right text-zinc-400 dark:bg-zinc-900 dark:text-zinc-600"
                style={{ minWidth: `${width + 2}ch` }}
              >
                {first + i}
              </span>
            )}
            <code className={startLine == null ? "px-3 whitespace-pre-wrap" : "pr-4 whitespace-pre"}>
              {highlight(line, pattern)}
            </code>
          </div>
        ))}
      </pre>
      {lines.length > limit && (
        <button
          onClick={() => setExpanded(true)}
          className="w-full border-t border-zinc-200 py-1 text-xs text-zinc-500 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
        >
          Show {lines.length - limit} more lines
        </button>
      )}
    </div>
  );
}
