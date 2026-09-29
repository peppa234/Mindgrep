"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { GraphEdge, GraphNode, Neighbourhood, NodeDetail, NodeOut, ProjectSummary } from "@/lib/types";

// One focal node and what surrounds it, never the whole graph: a force-directed hairball of
// every node looks impressive for four seconds and answers nothing.

const KINDS: { kind: string; label: string; fill: string; ring: string }[] = [
  { kind: "project", label: "Projects", fill: "#f59e0b", ring: "#b45309" },
  { kind: "technology", label: "Technologies", fill: "#38bdf8", ring: "#0369a1" },
  { kind: "idea", label: "Ideas", fill: "#fb7185", ring: "#be123c" },
  { kind: "note", label: "Notes", fill: "#34d399", ring: "#047857" },
  { kind: "concept", label: "Concepts", fill: "#e879f9", ring: "#a21caf" },
  { kind: "topic", label: "Tags", fill: "#a3e635", ring: "#4d7c0f" },
  { kind: "person", label: "People", fill: "#a78bfa", ring: "#6d28d9" },
  { kind: "package", label: "Packages", fill: "#a1a1aa", ring: "#52525b" },
];
const STYLE = Object.fromEntries(KINDS.map((k) => [k.kind, k]));
const DEFAULT_KINDS = KINDS.map((k) => k.kind).filter((k) => k !== "package");

const W = 900;
const H = 640;
const CX = W / 2;
const CY = H / 2;
const RINGS = [0, 170, 285];

interface Placed extends GraphNode {
  x: number;
  y: number;
  angle: number;
}

function layout(data: Neighbourhood, focal: number): Placed[] {
  const byDepth = new Map<number, GraphNode[]>();
  for (const node of data.nodes) byDepth.set(node.depth, [...(byDepth.get(node.depth) ?? []), node]);
  const placed = new Map<number, Placed>();
  const order = (n: GraphNode) => KINDS.findIndex((k) => k.kind === n.kind);

  const centre = data.nodes.find((n) => n.id === focal) ?? data.nodes[0];
  if (centre) placed.set(centre.id, { ...centre, x: CX, y: CY, angle: 0 });

  const first = [...(byDepth.get(1) ?? [])].sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name));
  first.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, first.length) - Math.PI / 2;
    placed.set(node.id, { ...node, angle, x: CX + RINGS[1] * Math.cos(angle), y: CY + RINGS[1] * Math.sin(angle) });
  });

  // Second ring: each node goes near the first-ring node(s) it hangs off, then the ring is
  // spread evenly in that order so labels do not pile up.
  const second = (byDepth.get(2) ?? []).map((node) => {
    const parents = data.edges
      .filter((e) => e.src === node.id || e.dst === node.id)
      .map((e) => placed.get(e.src === node.id ? e.dst : e.src))
      .filter((p): p is Placed => p != null && p.depth === 1);
    const x = parents.reduce((s, p) => s + Math.cos(p.angle), 0);
    const y = parents.reduce((s, p) => s + Math.sin(p.angle), 0);
    return { node, want: parents.length ? Math.atan2(y, x) : 0 };
  });
  second.sort((a, b) => a.want - b.want);
  second.forEach(({ node, want }, i) => {
    const even = (2 * Math.PI * i) / Math.max(1, second.length) - Math.PI;
    const angle = second.length > 12 ? even : want;
    placed.set(node.id, { ...node, angle, x: CX + RINGS[2] * Math.cos(angle), y: CY + RINGS[2] * Math.sin(angle) });
  });
  return [...placed.values()];
}

function truncate(text: string, n = 24) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

function hrefFor(node: { kind: string; id: number; meta: Record<string, unknown> }): string | null {
  if (node.kind === "project") return `/projects/${node.id}`;
  if (node.kind === "note" && node.meta.document_id != null) return `/documents/${node.meta.document_id}`;
  if (node.kind === "idea") return "/ideas?status=all";
  if (node.kind === "technology") return `/projects?uses=${encodeURIComponent(String(node.meta.name ?? ""))}`;
  return null;
}

function Detail({ node }: { node: NodeDetail }) {
  const relations = [
    ...Object.entries(node.outgoing).map(([type, items]) => ({ type, dir: "→", items })),
    ...Object.entries(node.incoming).map(([type, items]) => ({ type, dir: "←", items })),
  ];
  const link = hrefFor({ ...node, meta: { ...node.meta, name: node.name } });
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs tracking-wide text-zinc-500 uppercase">{node.kind}</p>
        <h2 className="font-semibold">{node.name}</h2>
        {typeof node.meta.status === "string" && <p className="text-xs text-zinc-500">status: {node.meta.status}</p>}
        {link && (
          <Link href={link} className="text-xs text-amber-700 hover:underline dark:text-amber-400">
            open {node.kind} →
          </Link>
        )}
      </div>
      <ul className="space-y-2">
        {relations.map(({ type, dir, items }) => (
          <li key={`${dir}${type}`}>
            <p className="text-xs text-zinc-500">
              {dir} {type.replace("_", " ")} ({items.length})
            </p>
            <p className="text-xs text-zinc-700 dark:text-zinc-300">
              {items
                .slice(0, 8)
                .map((i) => i.name)
                .join(", ")}
              {items.length > 8 ? ` +${items.length - 8}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Start({ onPick }: { onPick: (id: number) => void }) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  useEffect(() => {
    api.projects().then(setProjects).catch(() => undefined);
  }, []);
  return (
    <div className="space-y-3 rounded-lg border border-dashed border-zinc-300 p-6 text-sm dark:border-zinc-700">
      <p className="text-zinc-600 dark:text-zinc-400">
        Pick a starting point, or search for any technology, note, idea or person above.
      </p>
      <div className="flex flex-wrap gap-2">
        {projects.map((p) => (
          <button
            key={p.id}
            onClick={() => onPick(p.id)}
            className="rounded-full border border-amber-300 px-3 py-1 text-xs hover:bg-amber-50 dark:border-amber-800 dark:hover:bg-amber-500/10"
          >
            {p.name}
          </button>
        ))}
        {projects.length === 0 && <span className="text-zinc-400">No projects indexed yet.</span>}
      </div>
    </div>
  );
}

export function GraphView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const focal = params.get("node") ? Number(params.get("node")) : null;
  const depth = params.get("depth") === "2" ? 2 : 1;
  const [kinds, setKinds] = useState<string[]>(DEFAULT_KINDS);
  const [data, setData] = useState<Neighbourhood | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NodeOut[] | null>(null);

  useEffect(() => {
    if (focal == null) return;
    setError(null);
    api
      .neighbourhood(focal, depth, kinds, 50)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    api
      .node(focal)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [focal, depth, kinds]);

  function go(id: number, nextDepth = depth) {
    setResults(null);
    router.replace(`${pathname}?node=${id}${nextDepth === 2 ? "&depth=2" : ""}`);
  }

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      setResults(await api.searchNodes(query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const placed = useMemo(() => (data && focal != null ? layout(data, focal) : []), [data, focal]);
  const at = useMemo(() => new Map(placed.map((p) => [p.id, p])), [placed]);
  const touching = (edge: GraphEdge) => hover != null && (edge.src === hover || edge.dst === hover);
  const neighbours = useMemo(() => {
    const set = new Set<number>();
    if (hover == null || !data) return set;
    for (const e of data.edges) {
      if (e.src === hover) set.add(e.dst);
      if (e.dst === hover) set.add(e.src);
    }
    return set;
  }, [hover, data]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-xl">
          <h1 className="text-xl font-semibold tracking-tight">Graph</h1>
          <p className="text-sm text-zinc-500">
            One node and what it connects to, at most 50 at a time. Click any node to move there; every edge is a fact with
            evidence behind it.
          </p>
        </div>
        <form onSubmit={search} className="relative flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a node… e.g. redis"
            className="w-60 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-amber-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
          {results && (
            <ul className="absolute top-10 right-0 z-20 max-h-80 w-72 overflow-auto rounded-md border border-zinc-200 bg-white py-1 text-sm shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
              {results.length === 0 && <li className="px-3 py-1.5 text-zinc-500">No match.</li>}
              {results.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => go(r.id)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  >
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: STYLE[r.kind]?.fill ?? "#a1a1aa" }} />
                    <span className="truncate">{r.name}</span>
                    <span className="ml-auto text-xs text-zinc-400">{r.kind}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        {KINDS.map((k) => {
          const on = kinds.includes(k.kind);
          return (
            <label key={k.kind} className={`flex cursor-pointer items-center gap-1.5 ${on ? "" : "opacity-40"}`}>
              <input
                type="checkbox"
                className="sr-only"
                checked={on}
                onChange={() => setKinds(on ? kinds.filter((x) => x !== k.kind) : [...kinds, k.kind])}
              />
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.fill }} />
              {k.label}
            </label>
          );
        })}
        {focal != null && (
          <span className="ml-auto flex gap-1">
            {[1, 2].map((d) => (
              <button
                key={d}
                onClick={() => go(focal, d)}
                className={`rounded-md px-2 py-1 ${
                  depth === d ? "bg-zinc-200 dark:bg-zinc-800" : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                }`}
              >
                {d} hop{d === 2 ? "s" : ""}
              </button>
            ))}
          </span>
        )}
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>}
      {focal == null && <Start onPick={(id) => go(id)} />}

      {focal != null && (
        <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/40">
            {!data && <p className="p-4 text-sm text-zinc-500">Loading…</p>}
            {data && (
              <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full select-none" role="img" aria-label="Ego network">
                {RINGS.slice(1, depth + 1).map((r) => (
                  <circle key={r} cx={CX} cy={CY} r={r} fill="none" className="stroke-zinc-100 dark:stroke-zinc-800" />
                ))}
                {data.edges.map((edge) => {
                  const a = at.get(edge.src);
                  const b = at.get(edge.dst);
                  if (!a || !b) return null;
                  const lit = touching(edge);
                  return (
                    <line
                      key={`${edge.src}-${edge.dst}-${edge.type}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      strokeWidth={lit ? 2 : 1}
                      strokeDasharray={edge.confidence < 0.8 ? "4 3" : undefined}
                      className={lit ? "stroke-amber-500" : "stroke-zinc-300 dark:stroke-zinc-700"}
                      opacity={hover != null && !lit ? 0.35 : 1}
                    >
                      <title>{`${a.name} —${edge.type.replace("_", " ")}→ ${b.name} (${edge.evidence} piece${
                        edge.evidence === 1 ? "" : "s"
                      } of evidence, confidence ${edge.confidence.toFixed(2)})`}</title>
                    </line>
                  );
                })}
                {placed.map((node) => {
                  const style = STYLE[node.kind] ?? STYLE.package;
                  const centre = node.depth === 0;
                  const r = centre ? 16 : node.depth === 1 ? 9 : 6;
                  const dim = hover != null && hover !== node.id && !neighbours.has(node.id);
                  const right = Math.cos(node.angle) >= 0;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x},${node.y})`}
                      onMouseEnter={() => setHover(node.id)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => !centre && go(node.id)}
                      className={centre ? "" : "cursor-pointer"}
                      opacity={dim ? 0.3 : 1}
                    >
                      <circle r={r} fill={style.fill} stroke={style.ring} strokeWidth={centre ? 3 : 1.5} />
                      <text
                        x={centre ? 0 : right ? r + 5 : -(r + 5)}
                        y={centre ? r + 18 : 4}
                        textAnchor={centre ? "middle" : right ? "start" : "end"}
                        className={`fill-zinc-700 dark:fill-zinc-300 ${centre ? "text-[15px] font-semibold" : "text-[12px]"}`}
                      >
                        {centre ? node.name : truncate(node.name)}
                      </text>
                      <title>{`${node.kind}: ${node.name}`}</title>
                    </g>
                  );
                })}
              </svg>
            )}
            {data && (
              <p className="border-t border-zinc-200 px-3 py-1.5 text-xs text-zinc-400 dark:border-zinc-800">
                {data.nodes.length} nodes · {data.edges.length} relations
                {data.nodes.length >= 50 ? " · capped at 50, nearest first" : ""} · dashed = inferred (LLM or matching)
              </p>
            )}
          </div>
          <aside className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            {detail ? <Detail node={detail} /> : <p className="text-sm text-zinc-500">…</p>}
          </aside>
        </div>
      )}
    </div>
  );
}
