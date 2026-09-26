"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CATEGORY_STYLE } from "@/components/projects-view";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { Evidence, NodeDetail, Related } from "@/lib/types";

const CATEGORY_LABEL: Record<string, string> = {
  language: "Languages",
  framework: "Frameworks",
  database: "Databases",
  ai: "AI / ML",
  auth: "Auth & security",
  infra: "Infrastructure",
  library: "Libraries",
  tool: "Tooling",
};
const CATEGORY_ORDER = ["language", "framework", "database", "ai", "auth", "infra", "library", "tool"];

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  const href =
    evidence.document_id != null
      ? `/documents/${evidence.document_id}${evidence.chunk_ids[0] ? `#chunk-${evidence.chunk_ids[0]}` : ""}`
      : null;
  const file = evidence.path?.split("/").pop();
  return (
    <li className="flex items-baseline gap-2 text-xs">
      <span className="w-16 shrink-0 font-mono text-[10px] tracking-wide text-zinc-400 uppercase">{evidence.extractor}</span>
      <span className="min-w-0 truncate font-mono text-zinc-600 dark:text-zinc-400">{evidence.evidence}</span>
      {href && (
        <Link href={href} className="ml-auto shrink-0 font-mono text-zinc-400 hover:text-amber-700 hover:underline dark:hover:text-amber-400">
          {file}
          {evidence.line ? `:${evidence.line}` : ""}
        </Link>
      )}
    </li>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-xs font-medium tracking-wide text-zinc-500 uppercase">{title}</h2>
      {children}
    </section>
  );
}

export function ProjectView({ id }: { id: number }) {
  const [node, setNode] = useState<NodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api
      .node(id)
      .then(setNode)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  if (error) return <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>;
  if (!node) return <p className="text-sm text-zinc-500">Loading…</p>;

  const technologies = (node.outgoing.uses ?? []).filter((r) => r.kind === "technology");
  const groups = new Map<string, Related[]>();
  for (const tech of technologies) {
    const category = (tech.meta.category as string) ?? "library";
    groups.set(category, [...(groups.get(category) ?? []), tech]);
  }
  const packages = (node.outgoing.depends_on ?? []).filter((r) => r.kind === "package");
  const ownProjects = (node.outgoing.depends_on ?? []).filter((r) => r.kind === "project");
  const usedBy = (node.incoming.depends_on ?? []).filter((r) => r.kind === "project");
  const authors = node.incoming.authored ?? [];
  const notes = [...(node.incoming.mentions ?? []), ...(node.incoming.links_to ?? [])].filter((r) => r.kind === "note");
  const concepts = (node.outgoing.mentions ?? []).filter((r) => r.kind === "concept" || r.kind === "technology");

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href="/projects" className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            ← Projects
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">{node.name}</h1>
          <p className="font-mono text-xs text-zinc-500">{(node.meta.root as string) || "(source root)"}</p>
        </div>
        <Link
          href={`/chat?q=${encodeURIComponent(`How is ${node.name} structured, and what does it do?`)}`}
          className="rounded-md border border-zinc-200 px-3 py-1.5 text-sm hover:border-amber-400 dark:border-zinc-800"
        >
          Ask about this project
        </Link>
      </div>

      <Section title="Stack">
        {technologies.length === 0 && <p className="text-sm text-zinc-500">No technologies detected.</p>}
        <div className="space-y-3">
          {CATEGORY_ORDER.filter((c) => groups.has(c)).map((category) => (
            <div key={category} className="space-y-1.5">
              <h3 className="text-sm text-zinc-500">{CATEGORY_LABEL[category]}</h3>
              <ul className="space-y-1">
                {groups.get(category)!.map((tech) => (
                  <li key={tech.node_id} className="rounded-md border border-zinc-200 dark:border-zinc-800">
                    <button
                      onClick={() => setOpen(open === tech.node_id ? null : tech.node_id)}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                    >
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${CATEGORY_STYLE[category] ?? ""}`}>{tech.name}</span>
                      <span className="text-xs text-zinc-400">
                        {tech.evidence.length} piece{tech.evidence.length === 1 ? "" : "s"} of evidence
                        {tech.confidence < 1 ? ` · confidence ${tech.confidence}` : ""}
                      </span>
                      <span className="ml-auto text-xs text-zinc-400">{open === tech.node_id ? "hide" : "why?"}</span>
                    </button>
                    {open === tech.node_id && (
                      <ul className="space-y-1 border-t border-zinc-200 px-3 py-2 dark:border-zinc-800">
                        {tech.evidence.map((e) => (
                          <EvidenceLine key={e.edge_id} evidence={e} />
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      {(ownProjects.length > 0 || usedBy.length > 0) && (
        <Section title="Your other projects">
          <ul className="space-y-1 text-sm">
            {ownProjects.map((p) => (
              <li key={p.node_id}>
                depends on{" "}
                <Link href={`/projects/${p.node_id}`} className="font-medium hover:underline">
                  {p.name}
                </Link>
              </li>
            ))}
            {usedBy.map((p) => (
              <li key={p.node_id}>
                used by{" "}
                <Link href={`/projects/${p.node_id}`} className="font-medium hover:underline">
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {notes.length > 0 && (
        <Section title="Linked notes">
          <ul className="space-y-1 text-sm">
            {notes.map((note) => (
              <li key={`${note.node_id}-${note.evidence[0]?.edge_id}`} className="flex items-baseline gap-2">
                {note.meta.document_id != null ? (
                  <Link href={`/documents/${note.meta.document_id}`} className="hover:text-amber-700 hover:underline dark:hover:text-amber-400">
                    {note.name}
                  </Link>
                ) : (
                  note.name
                )}
                <span className="font-mono text-xs text-zinc-400">{note.evidence[0]?.evidence}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {concepts.length > 0 && (
        <Section title="Concepts in the README (LLM-extracted)">
          <div className="flex flex-wrap gap-1.5">
            {concepts.map((c) => (
              <span key={c.node_id} title={c.evidence[0]?.evidence ?? ""} className="rounded-full border border-dashed border-zinc-300 px-2 py-0.5 text-xs text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
                {c.name}
              </span>
            ))}
          </div>
        </Section>
      )}

      {authors.length > 0 && (
        <Section title="Commits">
          <ul className="space-y-1 text-sm">
            {authors.map((a) => {
              const meta = a.evidence[0]?.meta ?? {};
              return (
                <li key={a.node_id} className="flex items-baseline gap-2">
                  <span>{a.name}</span>
                  <span className="text-xs text-zinc-400">
                    {String(meta.commits ?? "?")} commits · first {relativeTime((meta.first as string) ?? null)} · last{" "}
                    {relativeTime((meta.last as string) ?? null)}
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {packages.length > 0 && (
        <Section title={`Declared dependencies (${packages.length})`}>
          <ul className="grid gap-x-6 gap-y-0.5 font-mono text-xs text-zinc-600 sm:grid-cols-2 dark:text-zinc-400">
            {packages.map((p) => (
              <li key={p.node_id} className="truncate" title={p.evidence[0]?.evidence ?? ""}>
                {p.name}
                {p.evidence.every((e) => e.meta.dev) && <span className="ml-1 text-zinc-400">(dev)</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
