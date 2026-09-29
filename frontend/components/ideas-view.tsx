"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { lineRange, relativeTime } from "@/lib/format";
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

export const STATUS_STYLE: Record<IdeaStatus, { label: string; chip: string }> = {
  unimplemented: {
    label: "never built",
    chip: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-500/10 dark:text-amber-300",
  },
  partial: {
    label: "partly built",
    chip: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-500/10 dark:text-sky-300",
  },
  implemented: {
    label: "built",
    chip: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  abandoned: {
    label: "abandoned",
    chip: "border-zinc-300 bg-zinc-100 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400",
  },
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

function StatusChip({ status }: { status: IdeaStatus }) {
  const style = STATUS_STYLE[status];
  return <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${style.chip}`}>{style.label}</span>;
}

function Bar({ value, title }: { value: number; title: string }) {
  return (
    <span className="inline-flex h-1.5 w-20 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800" title={title}>
      <span className="h-full bg-amber-500" style={{ width: pct(Math.min(1, value)) }} />
    </span>
  );
}

function CandidateRow({ candidate, chosen }: { candidate: IdeaCandidate; chosen: boolean }) {
  const best = candidate.best;
  return (
    <li className="space-y-1 py-2 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <Link href={`/projects/${candidate.project_id}`} className={`hover:underline ${chosen ? "font-medium" : ""}`}>
          {candidate.project}
        </Link>
        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
          <Bar value={candidate.coverage} title="Share of the idea's distinctive words found in this project" />
          {pct(candidate.coverage)} of the words
        </span>
        {candidate.similarity != null && (
          <span className="text-xs text-zinc-500" title="Reranker score of the idea against this project's closest chunk">
            similarity {candidate.similarity.toFixed(2)}
          </span>
        )}
        {candidate.linked && <span className="text-xs text-zinc-500">linked from the note</span>}
      </div>
      {candidate.matched.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {candidate.matched.slice(0, 12).map((word) => (
            <span key={word} className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {word}
            </span>
          ))}
        </div>
      )}
      {best && (
        <p className="text-xs text-zinc-500">
          closest code:{" "}
          <Link
            href={`/documents/${best.document_id}#chunk-${best.chunk_id}`}
            className="font-mono text-zinc-600 hover:text-amber-700 hover:underline dark:text-zinc-400 dark:hover:text-amber-400"
          >
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
    <div className="space-y-3 border-t border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800">
      {idea.origin === "declared" && (
        <p className="text-zinc-600 dark:text-zinc-400">
          The note says so in its frontmatter
          {idea.declared_status ? (
            <>
              : <code className="font-mono text-xs">status: {idea.declared_status}</code>
            </>
          ) : null}
          {idea.declared_project ? (
            <>
              , <code className="font-mono text-xs">implemented_by: {idea.declared_project}</code>
            </>
          ) : null}
          . Matching alone says <strong>{STATUS_STYLE[idea.matched_status].label}</strong>.
        </p>
      )}
      {idea.origin === "user" && (
        <p className="text-zinc-600 dark:text-zinc-400">
          You marked this{idea.user_note ? `: “${idea.user_note}”` : "."} Matching alone says{" "}
          <strong>{STATUS_STYLE[idea.matched_status].label}</strong>.
        </p>
      )}
      {idea.status === "unimplemented" && idea.origin === "match" && (
        <p className="text-zinc-600 dark:text-zinc-400">
          No project clears the bar
          {idea.signals.includes("similarity") ? " on the words it shares or on the reranker's similarity" : " on the words it shares"}.
        </p>
      )}
      {idea.missing.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">Distinctive words no project contains</h4>
          <div className="flex flex-wrap gap-1">
            {idea.missing.slice(0, 16).map((word) => (
              <span
                key={word}
                className="rounded border border-dashed border-zinc-300 px-1.5 py-0.5 font-mono text-[11px] text-zinc-500 dark:border-zinc-700"
              >
                {word}
              </span>
            ))}
          </div>
        </div>
      )}
      {idea.candidates.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">Closest projects</h4>
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {idea.candidates.map((c) => (
              <CandidateRow key={c.project_id} candidate={c} chosen={c.project_id === chosen} />
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-zinc-400">
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

  const button =
    "rounded-md border border-zinc-200 px-2 py-1 text-xs hover:border-amber-400 disabled:opacity-50 dark:border-zinc-800";
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-zinc-200 px-4 py-2 dark:border-zinc-800">
      <span className="text-xs text-zinc-500">Wrong? It is</span>
      <select
        value={project ?? ""}
        onChange={(e) => setProject(e.target.value ? Number(e.target.value) : null)}
        className="rounded-md border border-zinc-200 bg-white px-1.5 py-1 text-xs dark:border-zinc-800 dark:bg-zinc-900"
        aria-label="Project that implements it"
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button
        disabled={busy || project == null}
        className={button}
        onClick={() => run(() => api.overrideIdea(idea.id, { status: "implemented", project_id: project }))}
      >
        built there
      </button>
      <button
        disabled={busy || project == null}
        className={button}
        onClick={() => run(() => api.overrideIdea(idea.id, { status: "partial", project_id: project }))}
      >
        partly built there
      </button>
      <span className="text-xs text-zinc-400">or</span>
      <button disabled={busy} className={button} onClick={() => run(() => api.overrideIdea(idea.id, { status: "unimplemented" }))}>
        never built
      </button>
      <button disabled={busy} className={button} onClick={() => run(() => api.overrideIdea(idea.id, { status: "abandoned" }))}>
        abandoned
      </button>
      {idea.origin === "user" && (
        <button disabled={busy} className={`${button} ml-auto`} onClick={() => run(() => api.clearIdeaOverride(idea.id))}>
          back to automatic
        </button>
      )}
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

function IdeaCard({ idea, projects, onChange }: { idea: Idea; projects: ProjectSummary[]; onChange: (idea: Idea) => void }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const where = `/documents/${idea.document_id}${idea.chunk_id ? `#chunk-${idea.chunk_id}` : ""}`;
  return (
    <li className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/40">
      <div className="space-y-1.5 px-4 py-3">
        <div className="flex items-start gap-3">
          <h3 className="min-w-0 flex-1 font-medium">{idea.title}</h3>
          {idea.written_on && <span className="shrink-0 text-xs text-zinc-400 tabular-nums">{idea.written_on}</span>}
          <StatusChip status={idea.status} />
        </div>
        {idea.summary && <p className="line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">{idea.summary}</p>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
          <Link href={where} className="font-mono hover:text-amber-700 hover:underline dark:hover:text-amber-400">
            {idea.path}
            {idea.line ? `:${idea.line}` : ""}
          </Link>
          {idea.project && (idea.status === "implemented" || idea.status === "partial") && (
            <span>
              →{" "}
              <Link href={`/projects/${idea.project.id}`} className="font-medium text-zinc-700 hover:underline dark:text-zinc-300">
                {idea.project.name}
              </Link>
            </span>
          )}
          {idea.status === "unimplemented" && idea.closest && idea.closest.coverage + (idea.closest.similarity ?? 0) > 0.05 && (
            <span>
              closest: {idea.closest.project} ({pct(idea.closest.coverage)}
              {idea.closest.similarity != null ? `, sim ${idea.closest.similarity.toFixed(2)}` : ""})
            </span>
          )}
          {idea.origin !== "match" && <span className="italic">{idea.origin === "user" ? "marked by you" : "declared in the note"}</span>}
          <span className="ml-auto flex gap-3">
            {idea.node_id != null && (
              <Link href={`/graph?node=${idea.node_id}`} className="hover:text-zinc-900 dark:hover:text-zinc-100">
                graph
              </Link>
            )}
            <button onClick={() => setEditing(!editing)} className="hover:text-zinc-900 dark:hover:text-zinc-100">
              {editing ? "cancel" : "correct"}
            </button>
            <button onClick={() => setOpen(!open)} className="hover:text-zinc-900 dark:hover:text-zinc-100">
              {open ? "hide" : "why?"}
            </button>
          </span>
        </div>
      </div>
      {open && <Why idea={idea} />}
      {editing && (
        <Override
          idea={idea}
          projects={projects}
          onChange={(next) => {
            setEditing(false);
            onChange(next);
          }}
        />
      )}
    </li>
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-xl font-semibold tracking-tight">Ideas</h1>
          <p className="text-sm text-zinc-500">
            Everything you wrote down as an idea (notes tagged <code className="font-mono">#idea</code>, notes in an{" "}
            <code className="font-mono">ideas/</code> folder, lines starting with <code className="font-mono">Idea:</code>), checked
            against the code of your {summary?.projects ?? "…"} projects. “Never built” means no project comes close; open{" "}
            <em>why?</em> to see what was compared.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={sort}
            onChange={(e) => navigate({ sort: e.target.value as Sort })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            aria-label="Sort"
          >
            <option value="oldest">Oldest first</option>
            <option value="newest">Newest first</option>
            <option value="closest">How close you got</option>
          </select>
          <button
            onClick={refresh}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:border-amber-400 dark:border-zinc-700"
            title="Re-match every idea against every project"
          >
            Re-check
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => navigate({ status: t.value })}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
              tab === t.value
                ? "border-amber-500 text-zinc-900 dark:text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            }`}
          >
            {t.label}
            <span className="ml-1.5 text-xs text-zinc-400 tabular-nums">{counts[t.value] ?? 0}</span>
          </button>
        ))}
      </div>

      {notice && <p className="rounded-md bg-zinc-100 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">{notice}</p>}
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>}
      {!ideas && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {ideas && ideas.length === 0 && (
        <p className="text-sm text-zinc-500">
          No ideas found yet. Tag a note <code className="font-mono">#idea</code>, keep ideas in an{" "}
          <code className="font-mono">ideas/</code> folder, or start a line with <code className="font-mono">Idea:</code>, then
          re-index the source.
        </p>
      )}
      {ideas && ideas.length > 0 && shown.length === 0 && <p className="text-sm text-zinc-500">Nothing here.</p>}

      <ul className="space-y-3">
        {shown.map((idea) => (
          <IdeaCard key={idea.id} idea={idea} projects={projects} onChange={replace} />
        ))}
      </ul>

      {tab === "unimplemented" && shown.length > 0 && (
        <p className="text-xs text-zinc-400">
          Ask it in chat too:{" "}
          <Link href={`/chat?q=${encodeURIComponent("What ideas have I never implemented?")}`} className="underline">
            “What ideas have I never implemented?”
          </Link>
        </p>
      )}
    </div>
  );
}
