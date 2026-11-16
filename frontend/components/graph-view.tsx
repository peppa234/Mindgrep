"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";

import { LoadError } from "@/components/load-error";
import { GlassPanel } from "@/components/visual/glass-panel";
import { api, errorMessage } from "@/lib/api";
import type { GraphEdge, GraphNode, Neighbourhood, NodeDetail, NodeOut, ProjectSummary } from "@/lib/types";

// One focal node and what surrounds it, never the whole graph: a force-directed hairball of
// every node looks impressive for four seconds and answers nothing.

// Every node is knowledge, so every node is violet; kinds are told apart by shape (which
// also keeps the graph readable without colour). The one exception is meaning, not kind:
// an idea that was never built is a gap, so it is magenta.
type Shape = "square" | "circle" | "diamond" | "ring" | "hexagon" | "triangle" | "dot" | "box";
const KINDS: { kind: string; label: string; shape: Shape }[] = [
  { kind: "project", label: "Projects", shape: "square" },
  { kind: "technology", label: "Technologies", shape: "circle" },
  { kind: "idea", label: "Ideas", shape: "diamond" },
  { kind: "note", label: "Notes", shape: "ring" },
  { kind: "concept", label: "Concepts", shape: "hexagon" },
  { kind: "topic", label: "Tags", shape: "dot" },
  { kind: "person", label: "People", shape: "triangle" },
  { kind: "package", label: "Packages", shape: "box" },
];
const SHAPE = Object.fromEntries(KINDS.map((k) => [k.kind, k.shape])) as Record<string, Shape>;
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
  second.sort((a, b) => a.want - b.want || a.node.name.localeCompare(b.node.name));
  const angles =
    second.length > 12
      ? second.map((_, i) => (2 * Math.PI * i) / second.length - Math.PI)
      : fanOut(second.map((s) => s.want));
  second.forEach(({ node }, i) => {
    const angle = angles[i];
    placed.set(node.id, { ...node, angle, x: CX + RINGS[2] * Math.cos(angle), y: CY + RINGS[2] * Math.sin(angle) });
  });
  return [...placed.values()];
}

/**
 * The angle two neighbouring labels on the outer ring need between them. At the sides of
 * the ring labels stack, so a line's height is enough; toward the top and bottom they run
 * into each other lengthwise and need more.
 */
function labelGap(angle: number) {
  return Math.min(0.34, 22 / (RINGS[2] * Math.max(Math.abs(Math.cos(angle)), 0.05)));
}

/**
 * Nodes that hang off the same parent all want the parent's angle, which stacked their
 * labels on one spot. Keeps the order and pushes neighbours apart until every label has
 * its gap. Takes sorted angles; up to 12 of them always fit round the ring.
 */
function fanOut(wants: number[]): number[] {
  const angles = [...wants];
  const n = angles.length;
  if (n < 2) return angles;
  for (let pass = 0; pass < 80; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const distance = angles[j] - angles[i] + (j === 0 ? 2 * Math.PI : 0);
      const need = Math.max(labelGap(angles[i]), labelGap(angles[j]));
      if (distance < need - 1e-4) {
        const push = (need - distance) / 2;
        angles[i] -= push;
        angles[j] += push;
        moved = true;
      }
    }
    if (!moved) break;
  }
  return angles;
}

/**
 * How many characters of an inner-ring label fit before it runs into the outer ring. Only
 * matters at two hops: at the sides the rings are 115 units apart, at the top and bottom a
 * label has the whole chord.
 */
function innerLabelRoom(angle: number, offset: number, fontSize: number) {
  const reach = Math.sqrt(RINGS[2] ** 2 - (RINGS[1] * Math.sin(angle)) ** 2) - Math.abs(RINGS[1] * Math.cos(angle));
  return Math.max(6, Math.floor((reach - offset - 14) / (fontSize * 0.55)));
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

const isGap = (node: { kind: string; meta: Record<string, unknown> }) =>
  node.kind === "idea" && node.meta.status === "unimplemented";

function polygon(r: number, sides: number, rotate = -Math.PI / 2) {
  return Array.from({ length: sides }, (_, i) => {
    const a = rotate + (2 * Math.PI * i) / sides;
    return `${(r * Math.cos(a)).toFixed(2)},${(r * Math.sin(a)).toFixed(2)}`;
  }).join(" ");
}

/** A node glyph centred on 0,0. `fill` is a paint server id, or null for hollow shapes. */
function Glyph({ shape, r, fill, stroke, strokeWidth }: { shape: Shape; r: number; fill: string; stroke: string; strokeWidth: number }) {
  const common = { fill, stroke, strokeWidth };
  switch (shape) {
    case "square":
      return <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={r * 0.3} {...common} />;
    case "diamond":
      return <polygon points={polygon(r * 1.3, 4)} {...common} />;
    case "ring":
      return <circle r={r} fill="var(--bg-void)" stroke={stroke} strokeWidth={Math.max(2, strokeWidth + 1)} />;
    case "hexagon":
      return <polygon points={polygon(r * 1.1, 6, 0)} {...common} />;
    case "triangle":
      return <polygon points={polygon(r * 1.3, 3)} {...common} />;
    case "dot":
      return <circle r={r * 0.7} {...common} />;
    case "box":
      return <rect x={-r * 0.8} y={-r * 0.8} width={1.6 * r} height={1.6 * r} rx={2} fill="var(--bg-void)" stroke={stroke} strokeWidth={strokeWidth} />;
    default:
      return <circle r={r} {...common} />;
  }
}

function LegendGlyph({ shape }: { shape: Shape }) {
  return (
    <svg aria-hidden viewBox="-8 -8 16 16" className="h-3.5 w-3.5 overflow-visible">
      <Glyph shape={shape} r={5} fill="url(#node-knowledge)" stroke="var(--violet-300)" strokeWidth={1} />
    </svg>
  );
}

function Detail({ node }: { node: NodeDetail }) {
  const relations = [
    ...Object.entries(node.outgoing).map(([type, items]) => ({ type, dir: "→", items })),
    ...Object.entries(node.incoming).map(([type, items]) => ({ type, dir: "←", items })),
  ];
  const link = hrefFor({ ...node, meta: { ...node.meta, name: node.name } });
  return (
    <div className="space-y-4 text-sm">
      <div className="space-y-1">
        <p className="font-mono text-xs tracking-widest text-mid uppercase">{node.kind}</p>
        <h2 className="text-h3">{node.name}</h2>
        {typeof node.meta.status === "string" && (
          <p className="flex items-center gap-1.5 text-xs text-mid">
            {isGap(node) && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />}
            status: <span className="text-hi">{node.meta.status}</span>
          </p>
        )}
        {link && (
          <Link href={link} className="link text-xs">
            open {node.kind} →
          </Link>
        )}
      </div>
      <ul className="space-y-3">
        {relations.map(({ type, dir, items }) => (
          <li key={`${dir}${type}`} className="space-y-0.5">
            <p className="font-mono text-xs text-mid">
              {dir} {type.replace("_", " ")} ({items.length})
            </p>
            <p className="text-xs text-hi">
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
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    api
      .projects()
      .then(setProjects)
      .catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  if (error) return <LoadError error={error} onRetry={load} />;
  return (
    <GlassPanel glow={false} className="space-y-4 text-sm">
      <p className="text-mid">Pick a starting point, or search for any technology, note, idea or person above.</p>
      <div className="flex flex-wrap gap-2">
        {projects === null && <span className="text-mid">Loading…</span>}
        {projects?.map((p) => (
          <button key={p.id} type="button" onClick={() => onPick(p.id)} className="chip text-hi">
            {p.name}
          </button>
        ))}
        {projects?.length === 0 && <span className="text-mid">No projects indexed yet.</span>}
      </div>
    </GlassPanel>
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
  const [detailFailed, setDetailFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NodeOut[] | null>(null);
  // The SVG scales with its box, so on a phone 12-unit labels would render at ~5px:
  // there, glyphs and labels are drawn larger and names truncated sooner.
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (focal == null) return;
    setError(null);
    setDetailFailed(false);
    api
      .neighbourhood(focal, depth, kinds, 50)
      .then(setData)
      .catch((e) => {
        // Drop what was drawn: it is another node's neighbourhood, not this one's.
        setData(null);
        setError(errorMessage(e));
      });
    api
      .node(focal)
      .then(setDetail)
      .catch(() => {
        setDetail(null);
        setDetailFailed(true);
      });
  }, [focal, depth, kinds, attempt]);

  function go(id: number, nextDepth = depth) {
    setResults(null);
    setHover(null);
    router.replace(`${pathname}?node=${id}${nextDepth === 2 ? "&depth=2" : ""}`);
  }

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      setResults(await api.searchNodes(query.trim()));
    } catch (err) {
      setError(errorMessage(err));
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

  const onNodeKey = (e: KeyboardEvent, id: number) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      go(id);
    }
  };

  return (
    <div className="space-y-6">
      {/* Paint servers shared by the canvas and the legend. */}
      <svg aria-hidden className="absolute h-0 w-0">
        <defs>
          <radialGradient id="node-knowledge" cx="35%" cy="30%" r="75%">
            <stop offset="0%" style={{ stopColor: "var(--violet-300)" }} />
            <stop offset="60%" style={{ stopColor: "var(--violet-500)" }} />
            <stop offset="100%" style={{ stopColor: "var(--violet-600)" }} />
          </radialGradient>
          <radialGradient id="node-gap" cx="35%" cy="30%" r="75%">
            <stop offset="0%" style={{ stopColor: "color-mix(in srgb, var(--magenta-500) 45%, white)" }} />
            <stop offset="65%" style={{ stopColor: "var(--magenta-500)" }} />
            <stop offset="100%" style={{ stopColor: "color-mix(in srgb, var(--magenta-500) 70%, var(--bg-void))" }} />
          </radialGradient>
        </defs>
      </svg>

      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-xl space-y-2">
          <h1 className="text-h2">Graph</h1>
          <p className="text-mid">
            One node and what it connects to, at most 50 at a time. Click any node, or tab to it and press Enter, to move
            there; every edge is a fact with evidence behind it.
          </p>
        </div>
        <form onSubmit={search} className="relative" role="search">
          <label htmlFor="node-search" className="sr-only">
            Find a node
          </label>
          <input
            id="node-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setResults(null)}
            placeholder="Find a node… e.g. redis"
            className="field h-10 w-64 px-3 text-sm"
          />
          <AnimatePresence>
            {results && (
              <motion.ul
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
                data-lenis-prevent
                className="absolute top-12 right-0 z-20 max-h-80 w-72 overflow-auto rounded-xl border border-line-bright bg-elevated/95 py-1 text-sm shadow-glow-violet backdrop-blur-xl"
              >
                {results.length === 0 && <li className="px-3 py-2 text-mid">No match.</li>}
                {results.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => go(r.id)}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-hi transition-colors hover:bg-glass-knowledge"
                    >
                      <LegendGlyph shape={SHAPE[r.kind] ?? "circle"} />
                      <span className="truncate">{r.name}</span>
                      <span className="ml-auto font-mono text-xs text-mid">{r.kind}</span>
                    </button>
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
        </form>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs" role="group" aria-label="Node kinds shown">
        {KINDS.map((k) => {
          const on = kinds.includes(k.kind);
          return (
            <button
              key={k.kind}
              type="button"
              aria-pressed={on}
              onClick={() => setKinds(on ? kinds.filter((x) => x !== k.kind) : [...kinds, k.kind])}
              className={`chip ${on ? "border-line-bright bg-transparent text-hi" : "text-mid line-through decoration-mid/60"}`}
            >
              <LegendGlyph shape={k.shape} />
              {k.label}
            </button>
          );
        })}
        <span className="flex items-center gap-1.5 px-2 text-mid">
          <svg aria-hidden viewBox="-8 -8 16 16" className="h-3.5 w-3.5 overflow-visible">
            <Glyph shape="diamond" r={5} fill="url(#node-gap)" stroke="var(--magenta-500)" strokeWidth={1} />
          </svg>
          never built
        </span>
        {focal != null && (
          <div className="seg ml-auto" role="group" aria-label="Depth">
            {[1, 2].map((d) => (
              <button key={d} type="button" aria-pressed={depth === d} onClick={() => go(focal, d)}>
                {d} hop{d === 2 ? "s" : ""}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <LoadError error={error} onRetry={focal != null ? () => setAttempt((n) => n + 1) : undefined} />}
      {focal == null && <Start onPick={(id) => go(id)} />}

      {focal != null && (data || !error) && (
        <div className="grid gap-5 lg:grid-cols-[1fr_18rem]">
          <div className="overflow-hidden rounded-2xl border border-line bg-void/70 shadow-[inset_0_0_120px_rgba(139,92,246,0.06)]">
            {!data && <p className="p-4 text-sm text-mid">Loading…</p>}
            {data && (
              <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full select-none" role="group" aria-label={`Ego network of ${detail?.name ?? "the node"}`}>
                {RINGS.slice(1, depth + 1).map((r) => (
                  <circle key={r} cx={CX} cy={CY} r={r} fill="none" stroke="var(--border-glass)" strokeDasharray="2 6" />
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
                      stroke={lit ? "var(--cyan-400)" : "rgba(168, 139, 250, 0.3)"}
                      strokeWidth={lit ? 1.75 : 1}
                      strokeDasharray={edge.confidence < 0.8 ? "4 4" : undefined}
                      opacity={hover != null && !lit ? 0.25 : 1}
                      style={{
                        transition: "stroke 200ms ease, opacity 200ms ease",
                        filter: lit ? "drop-shadow(0 0 4px rgba(34, 211, 238, 0.85))" : undefined,
                      }}
                    >
                      <title>{`${a.name} —${edge.type.replace("_", " ")}→ ${b.name} (${edge.evidence} piece${
                        edge.evidence === 1 ? "" : "s"
                      } of evidence, confidence ${edge.confidence.toFixed(2)})`}</title>
                    </line>
                  );
                })}
                {placed.map((node) => {
                  const centre = node.depth === 0;
                  const r = (centre ? 16 : node.depth === 1 ? 9 : 6) * (compact ? 1.6 : 1);
                  const lit = hover === node.id;
                  const dim = hover != null && !lit && !neighbours.has(node.id) && !centre;
                  const right = Math.cos(node.angle) >= 0;
                  const gap = isGap(node);
                  const accent = gap ? "var(--magenta-500)" : "var(--violet-300)";
                  const label = `${node.kind}: ${node.name}${gap ? " (never built)" : ""}`;
                  const fontSize = centre ? (compact ? 30 : 20) : compact ? 24 : 15;
                  const longest = compact ? 14 : 22;
                  const fits = depth === 2 && node.depth === 1 ? Math.min(longest, innerLabelRoom(node.angle, r + 7, fontSize)) : longest;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x},${node.y})`}
                      onMouseEnter={() => setHover(node.id)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(node.id)}
                      onBlur={() => setHover(null)}
                      onClick={() => !centre && go(node.id)}
                      onKeyDown={centre ? undefined : (e) => onNodeKey(e, node.id)}
                      tabIndex={centre ? undefined : 0}
                      role={centre ? "img" : "link"}
                      aria-label={centre ? `Focus: ${label}` : `Move to ${label}`}
                      className={`graph-node outline-none ${centre ? "" : "cursor-pointer"}`}
                      opacity={dim ? 0.3 : 1}
                      style={{
                        transition: "opacity 200ms ease",
                        filter: centre
                          ? `drop-shadow(0 0 6px ${gap ? "rgba(217,70,239,0.9)" : "rgba(167,139,250,0.9)"}) drop-shadow(0 0 22px ${gap ? "rgba(217,70,239,0.55)" : "rgba(139,92,246,0.6)"})`
                          : lit
                            ? `drop-shadow(0 0 6px ${gap ? "rgba(217,70,239,0.7)" : "rgba(167,139,250,0.75)"})`
                            : undefined,
                      }}
                    >
                      {/* Keyboard focus ring: shown by CSS on :focus-visible. */}
                      <circle className="focus-ring" r={r + 7} fill="none" stroke="var(--focus-ring)" strokeWidth={2} />
                      <Glyph
                        shape={SHAPE[node.kind] ?? "circle"}
                        r={r}
                        fill={gap ? "url(#node-gap)" : "url(#node-knowledge)"}
                        stroke={accent}
                        strokeWidth={centre ? 2 : 1}
                      />
                      <text
                        x={centre ? 0 : right ? r + 7 : -(r + 7)}
                        y={centre ? r + (compact ? 34 : 22) : compact ? 8 : 4}
                        textAnchor={centre ? "middle" : right ? "start" : "end"}
                        fill={centre || lit ? "var(--text-hi)" : "var(--text-mid)"}
                        fontSize={fontSize}
                        className={centre ? "font-display font-medium" : ""}
                      >
                        {centre ? node.name : truncate(node.name, fits)}
                      </text>
                      <title>{label}</title>
                    </g>
                  );
                })}
              </svg>
            )}
            {data && (
              <p className="border-t border-line px-4 py-2 font-mono text-xs text-mid">
                {data.nodes.length} nodes · {data.edges.length} relations
                {data.nodes.length >= 50 ? " · capped at 50, nearest first" : ""} · dashed = inferred (LLM or matching)
              </p>
            )}
          </div>
          <GlassPanel as="aside" glow={false} aria-label="Selected node">
            {detail ? (
              <Detail node={detail} />
            ) : (
              <p className="text-sm text-mid">{detailFailed ? "This node's details did not load." : "Loading…"}</p>
            )}
          </GlassPanel>
        </div>
      )}
    </div>
  );
}
