"use client";

import { useEffect, useState } from "react";

import { ConnectionLines } from "@/components/visual/connection-lines";
import { GlassPanel } from "@/components/visual/glass-panel";
import { MemoryOrb } from "@/components/visual/memory-orb";
import { api } from "@/lib/api";

type Counts = { repos: number; notes: number; memories: number };

const LINKS = [
  { from: "orb", to: "repos" },
  { from: "orb", to: "notes" },
  { from: "orb", to: "memories" },
];

const format = (n: number) => new Intl.NumberFormat("en").format(n);

function Stat({ anchor, value, label, detail, className }: { anchor: string; value: string; label: string; detail: string; className: string }) {
  return (
    <div data-anchor={anchor} className={`z-10 ${className}`}>
      <GlassPanel padding="none" className="animate-float px-4 py-3 motion-off:animate-none sm:px-5 sm:py-4">
        <p className="font-mono text-xl text-hi tabular-nums sm:text-2xl">{value}</p>
        <p className="text-sm text-hi">{label}</p>
        <p className="hidden text-xs text-mid sm:block">{detail}</p>
      </GlassPanel>
    </div>
  );
}

/**
 * The hero's right half: the orb, and dashed connections running out to three live
 * counts read from the index (repositories with a detected project, Markdown notes, and
 * indexed chunks: the memories answers are built from).
 */
export function HeroStage() {
  const [counts, setCounts] = useState<Counts | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    Promise.all([api.stats(), api.projects()])
      .then(([stats, projects]) =>
        setCounts({ repos: projects.length, notes: stats.documents_by_kind.markdown ?? 0, memories: stats.chunks }),
      )
      .catch(() => setOffline(true));
  }, []);

  const show = (n: number | undefined) => (counts && n != null ? format(n) : "—");

  return (
    <div className="relative">
      <div className="relative mx-auto grid w-full max-w-[40rem] grid-cols-3 gap-3 sm:block sm:aspect-square">
        <div data-anchor="orb" data-anchor-shape="circle" data-anchor-radius="0.72" className="col-span-3 mx-auto my-[14%] w-[80%] sm:absolute sm:inset-[6%] sm:my-0 sm:w-auto">
          <MemoryOrb />
        </div>
        <Stat anchor="repos" value={show(counts?.repos)} label="repos" detail="projects detected" className="sm:absolute sm:top-[4%] sm:left-0" />
        <Stat anchor="notes" value={show(counts?.notes)} label="notes" detail="Markdown files" className="sm:absolute sm:top-[42%] sm:right-0" />
        <Stat anchor="memories" value={show(counts?.memories)} label="memories" detail="indexed chunks" className="sm:absolute sm:bottom-[2%] sm:left-[8%]" />
        <ConnectionLines links={LINKS} />
      </div>
      <p className="mt-4 flex items-center justify-center gap-2 font-mono text-xs text-mid" role="status">
        <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${offline ? "bg-gap" : counts ? "bg-live shadow-glow-cyan" : "border border-mid"}`} />
        {offline ? "index offline: start the API to see your counts" : counts ? "live from your index" : "reading your index…"}
      </p>
    </div>
  );
}
