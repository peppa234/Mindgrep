"use client";

import { Fragment, type ReactNode } from "react";

/**
 * The subset of Markdown answers use (paragraphs, lists, headings, **bold**, `code`, fenced
 * code) plus [n] citations rendered as chips. Built from React elements, never from HTML
 * strings: an answer quoting a source cannot inject markup. Tolerates a half-streamed
 * answer (an unclosed fence renders as code so far).
 */
export function Markdown({
  text,
  valid,
  onCite,
}: {
  text: string;
  valid: (n: number) => boolean;
  onCite: (n: number) => void;
}) {
  const blocks: ReactNode[] = [];
  const parts = text.split(/^```[^\n]*\n?/m);
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      blocks.push(
        <pre
          key={`code-${i}`}
          className="overflow-x-auto rounded-md border border-zinc-200 bg-white px-3 py-2 font-mono text-[12.5px] leading-5 dark:border-zinc-800 dark:bg-zinc-900/60"
        >
          {part.replace(/\n$/, "")}
        </pre>,
      );
    } else {
      blocks.push(...prose(part, `p-${i}`, valid, onCite));
    }
  });
  return <div className="space-y-3 text-[15px] leading-relaxed">{blocks}</div>;
}

function prose(text: string, key: string, valid: (n: number) => boolean, onCite: (n: number) => void) {
  const out: ReactNode[] = [];
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim());
  paragraphs.forEach((paragraph, p) => {
    const lines = paragraph.split("\n").filter((l) => l.trim());
    const isList = lines.every((l) => /^\s*(?:[-*]|\d+[.)])\s+/.test(l));
    if (isList) {
      const ordered = /^\s*\d/.test(lines[0]);
      const items = lines.map((l, j) => (
        <li key={j}>{inline(l.replace(/^\s*(?:[-*]|\d+[.)])\s+/, ""), valid, onCite)}</li>
      ));
      out.push(
        ordered ? (
          <ol key={`${key}-${p}`} className="list-decimal space-y-1 pl-5">
            {items}
          </ol>
        ) : (
          <ul key={`${key}-${p}`} className="list-disc space-y-1 pl-5 marker:text-zinc-400">
            {items}
          </ul>
        ),
      );
      return;
    }
    const heading = /^#{1,4}\s+(.*)$/.exec(lines[0] ?? "");
    if (heading && lines.length === 1) {
      out.push(
        <h4 key={`${key}-${p}`} className="font-semibold">
          {inline(heading[1], valid, onCite)}
        </h4>,
      );
      return;
    }
    // Lines inside a paragraph keep their breaks (graph answers are line-oriented).
    out.push(
      <p key={`${key}-${p}`}>
        {lines.map((line, j) => (
          <Fragment key={j}>
            {j > 0 && <br />}
            {inline(line, valid, onCite)}
          </Fragment>
        ))}
      </p>,
    );
  });
  return out;
}

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\[\d+(?:\s*[,;]\s*\d+)*\])/g;

function inline(text: string, valid: (n: number) => boolean, onCite: (n: number) => void): ReactNode[] {
  return text.split(INLINE).map((token, i) => {
    if (i % 2 === 0) return <Fragment key={i}>{token}</Fragment>;
    if (token.startsWith("`"))
      return (
        <code key={i} className="rounded bg-zinc-200/70 px-1 py-0.5 font-mono text-[0.85em] dark:bg-zinc-800">
          {token.slice(1, -1)}
        </code>
      );
    if (token.startsWith("**"))
      return (
        <strong key={i} className="font-semibold">
          {token.slice(2, -2)}
        </strong>
      );
    const numbers = token
      .slice(1, -1)
      .split(/[,;]/)
      .map((n) => Number(n.trim()));
    return (
      <Fragment key={i}>
        {numbers.map((n) =>
          valid(n) ? (
            <button
              key={n}
              type="button"
              onClick={() => onCite(n)}
              title={`Show source ${n}`}
              className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded bg-amber-100 px-1 align-middle font-mono text-[11px] font-medium text-amber-800 hover:bg-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:hover:bg-amber-500/30"
            >
              {n}
            </button>
          ) : null,
        )}
      </Fragment>
    );
  });
}
