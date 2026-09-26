"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ProjectSummary, StackTech } from "@/lib/types";

export const CATEGORY_STYLE: Record<string, string> = {
  language: "border-sky-300 text-sky-800 dark:border-sky-800 dark:text-sky-300",
  framework: "border-violet-300 text-violet-800 dark:border-violet-800 dark:text-violet-300",
  database: "border-emerald-300 text-emerald-800 dark:border-emerald-800 dark:text-emerald-300",
  ai: "border-fuchsia-300 text-fuchsia-800 dark:border-fuchsia-800 dark:text-fuchsia-300",
  auth: "border-rose-300 text-rose-800 dark:border-rose-800 dark:text-rose-300",
  infra: "border-amber-300 text-amber-800 dark:border-amber-800 dark:text-amber-300",
};
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const NEUTRAL = "border-zinc-200 text-zinc-600 dark:border-zinc-800 dark:text-zinc-400";

export function TechChip({ tech, onClick }: { tech: StackTech; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${tech.category ?? "technology"} · detected via ${tech.via.join(", ")}`}
      className={`rounded-full border px-2 py-0.5 text-xs ${CATEGORY_STYLE[tech.category ?? ""] ?? NEUTRAL} ${
        onClick ? "hover:bg-zinc-100 dark:hover:bg-zinc-900" : "cursor-default"
      }`}
    >
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-zinc-500">
            Detected from Git repositories and dependency manifests. Every technology is read from a manifest, a Dockerfile,
            an import or the files themselves: never guessed.
          </p>
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="uses… e.g. postgres"
            className="w-52 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-amber-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
          {uses && (
            <button type="button" onClick={() => filter("")} className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              clear
            </button>
          )}
        </form>
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>}
      {projects === null && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {projects?.length === 0 && (
        <p className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
          {uses ? (
            <>No project declares, imports or runs “{uses}”.</>
          ) : (
            <>
              No projects yet.{" "}
              <Link href="/sources" className="text-amber-700 underline dark:text-amber-400">
                Index a folder of repositories
              </Link>{" "}
              and they appear here.
            </>
          )}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {projects?.map((project) => (
          <article key={project.id} className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <div>
              <Link href={`/projects/${project.id}`} className="font-medium hover:text-amber-700 hover:underline dark:hover:text-amber-400">
                {project.name}
              </Link>
              <p className="font-mono text-xs text-zinc-500">
                {project.source_name}/{project.root || ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {project.technologies.map((tech) => (
                <TechChip key={tech.name} tech={tech} onClick={() => filter(tech.name)} />
              ))}
              {project.technologies.length === 0 && <span className="text-xs text-zinc-400">no technologies detected</span>}
            </div>
            <p className="text-xs text-zinc-400">
              {plural(project.package_count, "declared dependency", "declared dependencies")} ·{" "}
              {plural(project.manifests.length, "manifest", "manifests")}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
