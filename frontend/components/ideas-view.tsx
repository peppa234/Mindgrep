"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { GlassPanel } from "@/components/visual/glass-panel";
import { api } from "@/lib/api";
import { lineRange, relativeTime } from "@/lib/format";
import { EASE_MEMORY, revealChild, revealParent } from "@/lib/motion";
import type { Idea, IdeaCandidate, IdeaStatus, IdeaSummary, ProjectSummary } from "@/lib/types";

type Tab = IdeaStatus | "all";
type Sort = "oldest" | "newest" | "closest";

const TABS: { value: Tab; label: string }[] = [
  { value: "unimplemented", label: "Never built" },
  { value: "partial", label: "Partly built" },
  { value: "implemented", label: "Built" },
  { value: "abandoned", label: "Abandoned" },
  { value: "all", label: "All" },
];

// Magenta is the gap: filled for never built, an outline for partly built. Violet is
// knowledge realised in code. Abandoned ideas are neither.
export const STATUS_STYLE: Record<IdeaStatus, { label: string; dot: string }> = {
  unimplemented: { label: "never built", dot: "bg-gap" },
  partial: { label: "partly built", dot: "border border-magenta-500" },
  implemented: { label: "built", dot: "bg-knowledge" },
  abandoned: { label: "abandoned", dot: "border border-mid" },
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

function StatusChip({ status }: { status: IdeaStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <span className="chip shrink-0 text-hi">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

function Bar({ value, title }: { value: number; title: string }) {
  return (
    <span className="inline-flex h-1.5 w-20 overflow-hidden rounded-full bg-line" title={title}>
      <span className="h-full rounded-full bg-knowledge" style={{ width: pct(Math.min(1, value)) }} />
    </span>
  );
}

function Reveal({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: EASE_MEMORY }}
          className="overflow-hidden"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function CandidateRow({ candidate, chosen }: { candidate: IdeaCandidate; chosen: boolean }) {
  const best = candidate.best;
  return (
    <li className="space-y-1.5 py-2.5 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <Link href={`/projects/${candidate.project_id}`} className={`link ${chosen ? "font-medium" : ""}`}>
          {candidate.project}
        </Link>
        <span className="flex items-center gap-1.5 text-xs text-mid">
          <Bar value={candidate.coverage} title="Share of the idea's distinctive words found in this project" />
          {pct(candidate.coverage)} of the words
        </span>
        {candidate.similarity != null && (
          <span className="font-mono text-xs text-mid" title="Reranker score of the idea against this project's closest chunk">
            similarity {candidate.similarity.toFixed(2)}
          </span>
        )}
        {candidate.linked && <span className="text-xs text-mid">linked from the note</span>}
      </div>
      {candidate.matched.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {candidate.matched.slice(0, 12).map((word) => (
            <span key={word} className="chip py-0 font-mono text-[11px]">
              {word}
            </span>
          ))}
        </div>
      )}
      {best && (
        <p className="text-xs text-mid">
          closest code:{" "}
          <Link href={`/documents/${best.document_id}#chunk-${best.chunk_id}`} className="link font-mono">
            {best.path}
            {best.symbol ? ` :: ${best.symbol}` : ""} {lineRange(best.start_line, best.end_line)}
          </Link>
        </p>
      )}
    </li>
  );
}

function Why({ idea }: { idea: Idea }) {
  const chosen = idea.project?.id;
  return (
    <div className="space-y-4 border-t border-line px-5 py-4 text-sm">
      {idea.origin === "declared" && (
        <p className="text-mid">
          The note says so in its frontmatter
          {idea.declared_status ? (
            <>
              : <code className="font-mono text-xs text-hi">status: {idea.declared_status}</code>
            </>
          ) : null}
          {idea.declared_project ? (
            <>
              , <code className="font-mono text-xs text-hi">implemented_by: {idea.declared_project}</code>
            </>
          ) : null}
          . Matching alone says <strong className="text-hi">{STATUS_STYLE[idea.matched_status].label}</strong>.
        </p>
      )}
      {idea.origin === "user" && (
        <p className="text-mid">
          You marked this{idea.user_note ? `: “${idea.user_note}”` : "."} Matching alone says{" "}
          <strong className="text-hi">{STATUS_STYLE[idea.matched_status].label}</strong>.
        </p>
      )}
      {idea.status === "unimplemented" && idea.origin === "match" && (
        <p className="text-mid">
          No project clears the bar
          {idea.signals.includes("similarity") ? " on the words it shares or on the reranker's similarity" : " on the words it shares"}.
        </p>
      )}
      {idea.missing.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-mono text-[11px] tracking-widest text-mid uppercase">Distinctive words no project contains</h4>
          <div className="flex flex-wrap gap-1">
            {idea.missing.slice(0, 16).map((word) => (
              <span key={word} data-tone="gap" className="chip py-0 font-mono text-[11px]">
                {word}
              </span>
            ))}
          </div>
        </div>
      )}
      {idea.candidates.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-mono text-[11px] tracking-widest text-mid uppercase">Closest projects</h4>
          <ul className="divide-y divide-line">
            {idea.candidates.map((c) => (
              <CandidateRow key={c.project_id} candidate={c} chosen={c.project_id === chosen} />
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-mid">
        Checked {relativeTime(idea.matched_at)} with {idea.signals.join(" + ") || "no signal"}.
      </p>
    </div>
  );
}

function Override({
  idea,
  projects,
  onChange,
}: {
  idea: Idea;
  projects: ProjectSummary[];
  onChange: (idea: Idea) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const suggested = idea.project?.id ?? idea.closest?.project_id ?? projects[0]?.id ?? null;
  const [project, setProject] = useState<number | null>(suggested);

  async function run(action: () => Promise<Idea>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const button = "btn-ghost h-8 px-2.5 text-xs";
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">
      <span className="text-xs text-mid">Wrong? It is</span>
      <select
        value={project ?? ""}
        onChange={(e) => setProject(e.target.value ? Number(e.target.value) : null)}
        className="field h-8 rounded-lg px-2 text-xs"
        aria-label="Project that implements it"
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={busy || project == null}
        className={button}
        onClick={() => run(() => api.overrideIdea(idea.id, { status: "implemented", project_id: project }))}
      >
        built there
      </button>
      <button
        type="button"
        disabled={busy || project == null}
        className={button}
        onClick={() => run(() => api.overrideIdea(idea.id, { status: "partial", project_id: project }))}
      >
        partly built there
      </button>
      <span className="text-xs text-mid">or</span>
      <button type="button" disabled={busy} className={button} onClick={() => run(() => api.overrideIdea(idea.id, { status: "unimplemented" }))}>
        never built
      </button>
      <button type="button" disabled={busy} className={button} onClick={() => run(() => api.overrideIdea(idea.id, { status: "abandoned" }))}>
        abandoned
      </button>
      {idea.origin === "user" && (
        <button type="button" disabled={busy} className={`${button} ml-auto`} onClick={() => run(() => api.clearIdeaOverride(idea.id))}>
          back to automatic
        </button>
      )}
      {error && (
        <span className="alert py-1 text-xs" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

function IdeaCard({ idea, projects, onChange }: { idea: Idea; projects: ProjectSummary[]; onChange: (idea: Idea) => void }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const where = `/documents/${idea.document_id}${idea.chunk_id ? `#chunk-${idea.chunk_id}` : ""}`;
  const gap = idea.status === "unimplemented";
  return (
    <GlassPanel as="article" tone={gap ? "gap" : "neutral"} padding="none">
      <div className="space-y-2 px-5 py-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-3">
          <h3 className="min-w-0 flex-1 text-h3">{idea.title}</h3>
          <div className="flex items-center gap-3 sm:pt-0.5">
            {idea.written_on && <span className="shrink-0 font-mono text-xs text-mid tabular-nums">{idea.written_on}</span>}
            <StatusChip status={idea.status} />
          </div>
        </div>
        {idea.summary && <p className="line-clamp-2 text-sm text-mid">{idea.summary}</p>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-mid">
          <Link href={where} className="link font-mono">
            {idea.path}
            {idea.line ? `:${idea.line}` : ""}
          </Link>
          {idea.project && (idea.status === "implemented" || idea.status === "partial") && (
            <span>
              →{" "}
              <Link href={`/projects/${idea.project.id}`} className="link font-medium">
                {idea.project.name}
              </Link>
            </span>
          )}
          {gap && idea.closest && idea.closest.coverage + (idea.closest.similarity ?? 0) > 0.05 && (
            <span>
              closest: <span className="text-hi">{idea.closest.project}</span> ({pct(idea.closest.coverage)}
              {idea.closest.similarity != null ? `, sim ${idea.closest.similarity.toFixed(2)}` : ""})
            </span>
          )}
          {idea.origin !== "match" && <span className="italic">{idea.origin === "user" ? "marked by you" : "declared in the note"}</span>}
          <span className="ml-auto flex gap-1">
            {idea.node_id != null && (
              <Link href={`/graph?node=${idea.node_id}`} className="btn-ghost h-7 px-2 text-xs">
                graph
              </Link>
            )}
            <button type="button" aria-expanded={editing} onClick={() => setEditing(!editing)} className="btn-ghost h-7 px-2 text-xs">
              {editing ? "cancel" : "correct"}
            </button>
            <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="btn-ghost h-7 px-2 text-xs">
              {open ? "hide" : "why?"}
            </button>
          </span>
        </div>
      </div>
      <Reveal open={open}>
        <Why idea={idea} />
      </Reveal>
      <Reveal open={editing}>
        <Override
          idea={idea}
          projects={projects}
          onChange={(next) => {
            setEditing(false);
            onChange(next);
          }}
        />
      </Reveal>
    </GlassPanel>
  );
}

export function IdeasView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = (params.get("status") as Tab) || "unimplemented";
  const sort = (params.get("sort") as Sort) || "oldest";
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [summary, setSummary] = useState<IdeaSummary | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .ideas("all", sort)
      .then(setIdeas)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    api.ideaSummary().then(setSummary).catch(() => undefined);
  }, [sort]);

  useEffect(load, [load]);
  useEffect(() => {
    api.projects().then(setProjects).catch(() => undefined);
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: ideas?.length ?? 0 };
    for (const idea of ideas ?? []) c[idea.status] = (c[idea.status] ?? 0) + 1;
    return c;
  }, [ideas]);
  const shown = (ideas ?? []).filter((i) => tab === "all" || i.status === tab);

  function navigate(next: { status?: Tab; sort?: Sort }) {
    const query = new URLSearchParams(params.toString());
    if (next.status) query.set("status", next.status);
    if (next.sort) query.set("sort", next.sort);
    router.replace(`${pathname}?${query}`);
  }

  async function refresh() {
    setNotice(null);
    try {
      await api.refreshIdeas();
      setNotice("Re-matching every idea against every project; this page updates when you reload it.");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }

  function replace(next: Idea) {
    setIdeas((current) => current?.map((i) => (i.id === next.id ? next : i)) ?? null);
    api.ideaSummary().then(setSummary).catch(() => undefined);
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl space-y-2">
          <h1 className="text-h2">Ideas</h1>
          <p className="text-mid">
            Everything you wrote down as an idea (notes tagged <code className="font-mono text-hi">#idea</code>, notes in an{" "}
            <code className="font-mono text-hi">ideas/</code> folder, lines starting with{" "}
            <code className="font-mono text-hi">Idea:</code>), checked against the code of your {summary?.projects ?? "…"}{" "}
            projects. <span className="text-hi">Never built</span> means no project comes close; open <em>why?</em> to see what
            was compared.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={sort}
            onChange={(e) => navigate({ sort: e.target.value as Sort })}
            className="field h-9 rounded-lg px-2 text-sm"
            aria-label="Sort"
          >
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
            <option value="closest">How close you got</option>
          </select>
          <button type="button" onClick={refresh} className="btn-ghost h-9 px-3 text-sm" title="Re-match every idea against every project">
            Re-check
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-line" role="group" aria-label="Filter by status">
        {TABS.map((t) => {
          const active = tab === t.value;
          return (
            <button
              key={t.value}
              type="button"
              aria-pressed={active}
              onClick={() => navigate({ status: t.value })}
              className={`relative -mb-px px-3 py-2.5 text-sm transition-colors ${active ? "text-hi" : "text-mid hover:text-hi"}`}
            >
              {t.label}
              <span className="ml-1.5 font-mono text-xs text-mid tabular-nums">{counts[t.value] ?? 0}</span>
              {active && <span aria-hidden className="absolute inset-x-2 bottom-0 h-px bg-live shadow-glow-cyan" />}
            </button>
          );
        })}
      </div>

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!ideas && !error && <p className="text-sm text-mid">Loading…</p>}
      {ideas && ideas.length === 0 && (
        <p className="text-sm text-mid">
          No ideas found yet. Tag a note <code className="font-mono text-hi">#idea</code>, keep ideas in an{" "}
          <code className="font-mono text-hi">ideas/</code> folder, or start a line with{" "}
          <code className="font-mono text-hi">Idea:</code>, then re-index the source.
        </p>
      )}
      {ideas && ideas.length > 0 && shown.length === 0 && <p className="text-sm text-mid">Nothing here.</p>}

      <motion.ul key={tab} variants={revealParent} initial="hidden" animate="shown" className="space-y-4">
        {shown.map((idea) => (
          <motion.li key={idea.id} variants={revealChild}>
            <IdeaCard idea={idea} projects={projects} onChange={replace} />
          </motion.li>
        ))}
      </motion.ul>

      {tab === "unimplemented" && shown.length > 0 && (
        <p className="text-sm text-mid">
          Ask it in chat too:{" "}
          <Link href={`/chat?q=${encodeURIComponent("What ideas have I never implemented?")}`} className="link">
            “What ideas have I never implemented?”
          </Link>
        </p>
      )}
    </div>
  );
}
