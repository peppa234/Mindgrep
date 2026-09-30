"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { GlassPanel } from "@/components/visual/glass-panel";
import { api } from "@/lib/api";
import { SPRING_PRESS, revealChild, revealParent } from "@/lib/motion";
import { useMotionOff } from "@/lib/stores/motion";
import type { ProjectSummary, StackTech } from "@/lib/types";

export const CATEGORY_LABEL: Record<string, string> = {
  language: "Languages",
  framework: "Frameworks",
  database: "Databases",
  ai: "AI / ML",
  auth: "Auth & security",
  infra: "Infrastructure",
  library: "Libraries",
  tool: "Tooling",
};
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * A detected technology. Chips are neutral: categories are grouped, not colour-coded, so
 * hue keeps its meaning. The one that matches the active filter is cyan.
 */
export function TechChip({ tech, active = false, onClick }: { tech: StackTech; active?: boolean; onClick?: () => void }) {
  const title = `${tech.category ?? "technology"} · detected via ${tech.via.join(", ")}`;
  if (!onClick)
    return (
      <span className="chip" title={title} data-active={active}>
        {tech.name}
      </span>
    );
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={active} className="chip">
      {tech.name}
    </button>
  );
}

export function ProjectsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const uses = params.get("uses") ?? "";
  const [query, setQuery] = useState(uses);
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const still = useMotionOff();

  useEffect(() => {
    setQuery(uses);
    setProjects(null);
    api
      .projects(uses || undefined)
      .then(setProjects)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [uses]);

  function filter(value: string) {
    router.replace(value.trim() ? `${pathname}?uses=${encodeURIComponent(value.trim())}` : pathname);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    filter(query);
  }

  const matches = (tech: StackTech) => uses !== "" && tech.name.toLowerCase().includes(uses.toLowerCase());

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl space-y-2">
          <h1 className="text-h2">Projects</h1>
          <p className="text-mid">
            Detected from Git repositories and dependency manifests. Every technology is read from a manifest, a Dockerfile,
            an import or the files themselves: never guessed.
          </p>
        </div>
        <form onSubmit={submit} className="flex items-center gap-2" role="search">
          <label htmlFor="uses" className="sr-only">
            Filter projects by technology
          </label>
          <input
            id="uses"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="uses… e.g. postgres"
            className="field h-10 w-56 px-3 text-sm"
          />
          {uses && (
            <button type="button" onClick={() => filter("")} className="btn-ghost h-10 px-3 text-sm">
              Clear
            </button>
          )}
        </form>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {projects === null && !error && <p className="text-sm text-mid">Loading…</p>}
      {projects?.length === 0 && (
        <GlassPanel glow={false} className="text-center text-sm text-mid">
          {uses ? (
            <>No project declares, imports or runs “{uses}”.</>
          ) : (
            <>
              No projects yet.{" "}
              <Link href="/sources" className="link">
                Index a folder of repositories
              </Link>{" "}
              and they appear here.
            </>
          )}
        </GlassPanel>
      )}

      {projects && projects.length > 0 && (
        <motion.ul
          variants={revealParent}
          initial="hidden"
          animate="shown"
          className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
          aria-label={uses ? `Projects using ${uses}` : "Projects"}
        >
          {projects.map((project) => (
            <motion.li key={project.id} variants={revealChild} className="flex">
              <motion.div whileHover={still ? undefined : { y: -4 }} transition={SPRING_PRESS} className="flex w-full">
                <GlassPanel as="article" className="flex w-full flex-col gap-4">
                  <div className="space-y-1">
                    <h2 className="text-h3">
                      <Link href={`/projects/${project.id}`} className="rounded-sm hover:text-violet-300">
                        {project.name}
                      </Link>
                    </h2>
                    <p className="truncate font-mono text-xs text-mid">
                      {project.source_name}/{project.root || ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {project.technologies.map((tech) => (
                      <TechChip key={tech.name} tech={tech} active={matches(tech)} onClick={() => filter(tech.name)} />
                    ))}
                    {project.technologies.length === 0 && <span className="text-xs text-mid">no technologies detected</span>}
                  </div>
                  <p className="mt-auto border-t border-line pt-3 font-mono text-xs text-mid">
                    {plural(project.package_count, "dependency", "dependencies")} ·{" "}
                    {plural(project.manifests.length, "manifest", "manifests")}
                  </p>
                </GlassPanel>
              </motion.div>
            </motion.li>
          ))}
        </motion.ul>
      )}
    </div>
  );
}
