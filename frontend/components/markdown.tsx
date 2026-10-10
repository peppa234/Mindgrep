"use client";

import { Fragment, type ReactNode } from "react";

import { CodeBlock } from "@/components/code-block";

type Cite = {
  valid: (n: number) => boolean;
  onCite: (n: number) => void;
  /** The citation whose source is open in the panel. */
  active?: number | null;
  /** While streaming, each new word fades in. */
  streaming?: boolean;
};

/**
 * The subset of Markdown answers use (paragraphs, lists, headings, **bold**, `code`, fenced
 * code) plus [n] citations rendered as chips. Built from React elements, never from HTML
 * strings: an answer quoting a source cannot inject markup. Tolerates a half-streamed
 * answer (an unclosed fence renders as code so far).
 */
export function Markdown({ text, valid, onCite, active = null, streaming = false }: { text: string } & Cite) {
  const cite: Cite = { valid, onCite, active, streaming };
  const blocks: ReactNode[] = [];
  // Splitting on the fence with its info string captured yields, per fence pair:
  // text, opening language, code, closing info (unused), text, …
  const parts = text.split(/^```([^\n]*)\n?/m);
  parts.forEach((part, i) => {
    const slot = i % 4;
    if (slot === 2) {
      blocks.push(
        <CodeBlock key={`code-${i}`} content={part.replace(/\n$/, "")} startLine={null} language={parts[i - 1]?.trim() || null} />,
      );
    } else if (slot === 0) {
      blocks.push(...prose(part, `p-${i}`, cite));
    }
  });
  return <div className="space-y-3 text-[0.9375rem] leading-relaxed text-hi">{blocks}</div>;
}

function prose(text: string, key: string, cite: Cite) {
  const out: ReactNode[] = [];
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim());
  paragraphs.forEach((paragraph, p) => {
    const lines = paragraph.split("\n").filter((l) => l.trim());
    const isList = lines.every((l) => /^\s*(?:[-*]|\d+[.)])\s+/.test(l));
    if (isList) {
      const ordered = /^\s*\d/.test(lines[0]);
      const items = lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*(?:[-*]|\d+[.)])\s+/, ""), cite)}</li>);
      out.push(
        ordered ? (
          <ol key={`${key}-${p}`} className="list-decimal space-y-1 pl-5 marker:text-mid">
            {items}
          </ol>
        ) : (
          <ul key={`${key}-${p}`} className="list-disc space-y-1 pl-5 marker:text-mid">
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
          {inline(heading[1], cite)}
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
            {inline(line, cite)}
          </Fragment>
        ))}
      </p>,
    );
  });
  return out;
}

/** Plain text; while streaming, one span per word so only newly arrived words animate. */
function words(text: string, key: number, streaming: boolean): ReactNode {
  if (!streaming) return <Fragment key={key}>{text}</Fragment>;
  return (
    <Fragment key={key}>
      {text.split(/(\s+)/).map((w, k) =>
        w.trim() ? (
          <span key={k} className="animate-word-in">
            {w}
          </span>
        ) : (
          w
        ),
      )}
    </Fragment>
  );
}

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\[\d+(?:\s*[,;]\s*\d+)*\])/g;

function inline(text: string, cite: Cite): ReactNode[] {
  return text.split(INLINE).map((token, i) => {
    if (i % 2 === 0) return words(token, i, Boolean(cite.streaming));
    if (token.startsWith("`"))
      return (
        <code key={i} className="rounded-md border border-line bg-elevated px-1 py-0.5 font-mono text-[0.85em] text-hi">
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
          cite.valid(n) ? (
            <CitationChip key={n} n={n} active={cite.active === n} onClick={() => cite.onCite(n)} />
          ) : null,
        )}
      </Fragment>
    );
  });
}

/** [n]: violet (a memory) at rest, cyan and glowing on hover and while its source is open. */
export function CitationChip({ n, active, onClick }: { n: number; active: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`Show source ${n}`}
      className={`mx-0.5 inline-flex h-[19px] min-w-[19px] -translate-y-px items-center justify-center rounded-md border px-1 align-middle font-mono text-xs font-medium transition-[color,border-color,box-shadow,background-color] duration-200 ${
        active
          ? "border-cyan-400/70 bg-[var(--surface-live)] text-cyan-400 shadow-glow-cyan"
          : "border-violet-400/40 bg-violet-500/10 text-violet-300 hover:border-cyan-400/70 hover:bg-[var(--surface-live)] hover:text-cyan-400 hover:shadow-glow-cyan"
      }`}
    >
      {n}
    </button>
  );
}
