"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { CATEGORY_LABEL } from "@/components/projects-view";
import { GlassPanel } from "@/components/visual/glass-panel";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { EASE_MEMORY } from "@/lib/motion";
import type { Evidence, NodeDetail, Related } from "@/lib/types";

const CATEGORY_ORDER = ["language", "framework", "database", "ai", "auth", "infra", "library", "tool"];

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  const href =
    evidence.document_id != null
      ? `/documents/${evidence.document_id}${evidence.chunk_ids[0] ? `#chunk-${evidence.chunk_ids[0]}` : ""}`
      : null;
  const file = evidence.path?.split("/").pop();
  return (
    <li className="flex items-baseline gap-3 text-xs">
      <span className="w-16 shrink-0 font-mono text-[10px] tracking-widest text-mid uppercase">{evidence.extractor}</span>
      <span className="min-w-0 truncate font-mono text-hi">{evidence.evidence}</span>
      {href && (
        <Link href={href} className="link ml-auto shrink-0 font-mono">
          {file}
          {evidence.line ? `:${evidence.line}` : ""}
        </Link>
      )}
    </li>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <GlassPanel as="section" glow={false} className="space-y-4">
      <h2 className="font-mono text-[11px] font-normal tracking-widest text-mid uppercase">{title}</h2>
      {children}
    </GlassPanel>
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

  if (error)
    return (
      <p className="alert" role="alert">
        {error}
      </p>
    );
  if (!node) return <p className="text-sm text-mid">Loading…</p>;

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
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-6 pb-2">
        <div className="space-y-2">
          <Link href="/projects" className="text-sm text-mid hover:text-hi">
            ← Projects
          </Link>
          <h1 className="text-h2">{node.name}</h1>
          <p className="font-mono text-xs text-mid">{(node.meta.root as string) || "(source root)"}</p>
        </div>
        <div className="flex gap-2">
          <Link href={`/graph?node=${node.id}`} className="btn-ghost h-9 px-3 text-sm">
            Graph
          </Link>
          <Link
            href={`/chat?q=${encodeURIComponent(`How is ${node.name} structured, and what does it do?`)}`}
            className="btn-ghost h-9 px-3 text-sm"
          >
            Ask about this project
          </Link>
        </div>
      </div>

      <Section title="Stack">
        {technologies.length === 0 && <p className="text-sm text-mid">No technologies detected.</p>}
        <div className="grid gap-6 md:grid-cols-2">
          {CATEGORY_ORDER.filter((c) => groups.has(c)).map((category) => (
            <div key={category} className="space-y-2">
              <h3 className="text-sm font-medium tracking-normal text-hi">{CATEGORY_LABEL[category]}</h3>
              <ul className="space-y-1.5">
                {groups.get(category)!.map((tech) => {
                  const expanded = open === tech.node_id;
                  return (
                    <li key={tech.node_id} className="rounded-xl border border-line">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => setOpen(expanded ? null : tech.node_id)}
                        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-glass"
                      >
                        <span className="chip text-hi">{tech.name}</span>
                        <span className="text-xs text-mid">
                          {tech.evidence.length} piece{tech.evidence.length === 1 ? "" : "s"} of evidence
                          {tech.confidence < 1 ? ` · confidence ${tech.confidence}` : ""}
                        </span>
                        <span className="ml-auto text-xs text-mid">{expanded ? "hide" : "why?"}</span>
                      </button>
                      <AnimatePresence initial={false}>
                        {expanded && (
                          <motion.ul
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.3, ease: EASE_MEMORY }}
                            className="space-y-1.5 overflow-hidden border-t border-line px-3 py-2"
                          >
                            {tech.evidence.map((e) => (
                              <EvidenceLine key={e.edge_id} evidence={e} />
                            ))}
                          </motion.ul>
                        )}
                      </AnimatePresence>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-6 md:grid-cols-2">
        {(ownProjects.length > 0 || usedBy.length > 0) && (
          <Section title="Your other projects">
            <ul className="space-y-1.5 text-sm text-mid">
              {ownProjects.map((p) => (
                <li key={p.node_id}>
                  depends on{" "}
                  <Link href={`/projects/${p.node_id}`} className="link">
                    {p.name}
                  </Link>
                </li>
              ))}
              {usedBy.map((p) => (
                <li key={p.node_id}>
                  used by{" "}
                  <Link href={`/projects/${p.node_id}`} className="link">
                    {p.name}
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {notes.length > 0 && (
          <Section title="Linked notes">
            <ul className="space-y-1.5 text-sm">
              {notes.map((note) => (
                <li key={`${note.node_id}-${note.evidence[0]?.edge_id}`} className="flex items-baseline gap-2">
                  {note.meta.document_id != null ? (
                    <Link href={`/documents/${note.meta.document_id}`} className="link">
                      {note.name}
                    </Link>
                  ) : (
                    <span className="text-hi">{note.name}</span>
                  )}
                  <span className="truncate font-mono text-xs text-mid">{note.evidence[0]?.evidence}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {concepts.length > 0 && (
          <Section title="Concepts in the README (LLM-extracted)">
            <div className="flex flex-wrap gap-1.5">
              {concepts.map((c) => (
                <span key={c.node_id} title={c.evidence[0]?.evidence ?? ""} className="chip border-dashed">
                  {c.name}
                </span>
              ))}
            </div>
          </Section>
        )}

        {authors.length > 0 && (
          <Section title="Commits">
            <ul className="space-y-1.5 text-sm">
              {authors.map((a) => {
                const meta = a.evidence[0]?.meta ?? {};
                return (
                  <li key={a.node_id} className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-hi">{a.name}</span>
                    <span className="text-xs text-mid">
                      {String(meta.commits ?? "?")} commits · first {relativeTime((meta.first as string) ?? null)} · last{" "}
                      {relativeTime((meta.last as string) ?? null)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Section>
        )}
      </div>

      {packages.length > 0 && (
        <Section title={`Declared dependencies (${packages.length})`}>
          <ul className="grid gap-x-6 gap-y-1 font-mono text-xs text-hi sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((p) => (
              <li key={p.node_id} className="truncate" title={p.evidence[0]?.evidence ?? ""}>
                {p.name}
                {p.evidence.every((e) => e.meta.dev) && <span className="ml-1 text-mid">(dev)</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
