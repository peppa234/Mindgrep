"use client";

import { Highlight } from "prism-react-renderer";
import { Fragment, type ReactNode, useMemo, useState } from "react";

import { EMPTY_THEME, prismLanguage, tokenClass } from "@/lib/code-theme";

function mark(text: string, pattern: RegExp | null): ReactNode {
  if (!pattern || !text) return text;
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="mark-term">
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/**
 * Source text with real line numbers (from the file, not from 1), syntax highlighting when
 * the language has a grammar, and query terms marked. Only the visible lines are tokenized.
 */
export function CodeBlock({
  content,
  startLine,
  language,
  terms = [],
  maxLines,
}: {
  content: string;
  startLine: number | null;
  language?: string | null;
  terms?: string[];
  maxLines?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const all = content.split("\n");
  const limit = maxLines && !expanded ? maxLines : all.length;
  const visible = all.slice(0, limit).join("\n");
  const pattern = useMemo(() => {
    const words = terms.filter((t) => t.length >= 3).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return words.length ? new RegExp(`(${words.join("|")})`, "gi") : null;
  }, [terms]);
  const first = startLine ?? 1;
  const width = String(first + all.length).length;
  const grammar = prismLanguage(language);
  const numbered = startLine != null;

  const renderLine = (key: number, children: ReactNode) => (
    <div key={key} className="flex">
      {numbered && (
        <span
          aria-hidden
          className="sticky left-0 shrink-0 bg-[var(--code-bg)] pr-3 pl-3 text-right text-[var(--code-gutter)] select-none"
          style={{ minWidth: `${width + 2}ch` }}
        >
          {first + key}
        </span>
      )}
      <code className={numbered ? "pr-4 whitespace-pre" : "px-4 whitespace-pre-wrap"}>{children}</code>
    </div>
  );

  return (
    <div className="code-surface overflow-hidden">
      <pre data-lenis-prevent className="overflow-x-auto py-3 font-mono text-[0.8125rem] leading-5">
        {grammar ? (
          <Highlight code={visible} language={grammar} theme={EMPTY_THEME}>
            {({ tokens }) =>
              tokens.map((line, i) =>
                renderLine(
                  i,
                  line.length === 1 && line[0].empty
                    ? " "
                    : line.map((token, j) => (
                        <span key={j} className={tokenClass(token.types)}>
                          {mark(token.content, pattern)}
                        </span>
                      )),
                ),
              )
            }
          </Highlight>
        ) : (
          visible.split("\n").map((line, i) => renderLine(i, line ? mark(line, pattern) : " "))
        )}
      </pre>
      {all.length > limit && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="w-full border-t border-line py-1.5 text-xs text-mid transition-colors hover:bg-glass hover:text-hi"
        >
          Show {all.length - limit} more lines
        </button>
      )}
    </div>
  );
}
