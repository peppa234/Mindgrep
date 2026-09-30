"use client";

import Link from "next/link";

import { Reveal, RevealItem } from "@/components/landing/reveal";
import { ConnectionLines } from "@/components/visual/connection-lines";
import { GlassPanel, type GlassTone } from "@/components/visual/glass-panel";

const FEATURES: { id: string; label: string; title: string; body: string; href: string; cta: string; tone: GlassTone }[] = [
  {
    id: "chat",
    label: "chat",
    title: "Answers that cite the line",
    body: "Ask in plain words. Every claim links to the passage, file and line it came from, and when the answer is not in your memory it says so.",
    href: "/chat",
    cta: "Ask your memory",
    tone: "knowledge",
  },
  {
    id: "search",
    label: "search",
    title: "Hybrid search over everything",
    body: "Vectors, full text and symbol names fused and reranked, across code, Markdown and PDFs. Describe the thing, not the filename.",
    href: "/search",
    cta: "Search",
    tone: "neutral",
  },
  {
    id: "graph",
    label: "graph",
    title: "A graph with evidence",
    body: "Projects, technologies, notes and people, connected from manifests, imports and git history. Every edge shows why it exists.",
    href: "/graph",
    cta: "Explore the graph",
    tone: "neutral",
  },
  {
    id: "ideas",
    label: "gaps",
    title: "Ideas you never built",
    body: "Every idea you wrote down, checked against the code of every project. The ones no project comes close to are surfaced, not buried.",
    href: "/ideas",
    cta: "See the gaps",
    tone: "gap",
  },
];

const LINKS = [
  { from: "f-chat", to: "f-search" },
  { from: "f-chat", to: "f-graph" },
  { from: "f-search", to: "f-ideas" },
  { from: "f-graph", to: "f-ideas" },
];

/** Four ways into one memory, wired together by the connection motif. */
export function FeatureGrid() {
  return (
    <div className="relative">
      <Reveal as="ul" className="grid gap-10 md:grid-cols-2 md:gap-x-24 md:gap-y-16">
        {FEATURES.map((f) => (
          <RevealItem as="li" key={f.id} className="flex">
            <div data-anchor={`f-${f.id}`} className="relative z-10 flex w-full">
              <GlassPanel as="article" tone={f.tone} padding="lg" className="flex w-full flex-col gap-3">
                <p className="flex items-center gap-2 font-mono text-[11px] tracking-widest text-mid uppercase">
                  <span
                    aria-hidden
                    className={`h-1.5 w-1.5 rounded-full ${f.tone === "gap" ? "bg-gap" : "bg-knowledge"}`}
                  />
                  {f.label}
                </p>
                <h3 className="text-h3">{f.title}</h3>
                <p className="text-mid">{f.body}</p>
                <Link prefetch={false} href={f.href} className="link mt-auto pt-2 text-sm">
                  {f.cta} →
                </Link>
              </GlassPanel>
            </div>
          </RevealItem>
        ))}
      </Reveal>
      <ConnectionLines links={LINKS} className="hidden md:block" />
    </div>
  );
}
