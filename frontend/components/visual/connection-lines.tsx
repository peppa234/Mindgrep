"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useMotionOff } from "@/lib/stores/motion";

export type Connection = { from: string; to: string };

type Path = { id: string; d: string };

type Box = { x: number; y: number; w: number; h: number; circle: boolean; radius: number };

/** Where the segment from the box's centre toward (tx, ty) leaves the box (or circle). */
function exit(box: Box, tx: number, ty: number): [number, number] {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  const len = Math.hypot(dx, dy) || 1;
  if (box.circle) {
    const r = (Math.min(box.w, box.h) / 2) * box.radius;
    return [cx + (dx / len) * r, cy + (dy / len) * r];
  }
  const sx = dx === 0 ? Infinity : box.w / 2 / Math.abs(dx);
  const sy = dy === 0 ? Infinity : box.h / 2 / Math.abs(dy);
  const s = Math.min(sx, sy);
  return [cx + dx * s, cy + dy * s];
}

/**
 * The signature motif: dashed bezier curves between elements, dashes travelling along
 * them and small cyan dots riding each path (data in motion). Place it inside a positioned
 * container; it connects descendants marked data-anchor="<id>". A circular anchor can say
 * data-anchor-shape="circle" (and data-anchor-radius, a 0–1 scale). Reduced motion keeps
 * the lines and stops the dashes and dots.
 */
export function ConnectionLines({
  links,
  dots = true,
  className = "",
}: {
  links: Connection[];
  dots?: boolean;
  className?: string;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [paths, setPaths] = useState<Path[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const off = useMotionOff();

  const measure = useCallback(() => {
    const root = svg.current?.parentElement;
    if (!root) return;
    const origin = root.getBoundingClientRect();
    const box = (id: string): Box | null => {
      const el = root.querySelector<HTMLElement>(`[data-anchor="${id}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        x: r.left - origin.left,
        y: r.top - origin.top,
        w: r.width,
        h: r.height,
        circle: el.dataset.anchorShape === "circle",
        radius: Number(el.dataset.anchorRadius ?? 1),
      };
    };
    const next: Path[] = [];
    links.forEach((link, i) => {
      const a = box(link.from);
      const b = box(link.to);
      if (!a || !b || !a.w || !b.w) return;
      const [x1, y1] = exit(a, b.x + b.w / 2, b.y + b.h / 2);
      const [x2, y2] = exit(b, a.x + a.w / 2, a.y + a.h / 2);
      // Bend along the dominant axis so curves leave and arrive square to the edges.
      const horizontal = Math.abs(x2 - x1) >= Math.abs(y2 - y1);
      const k = 0.45;
      const c1 = horizontal ? [x1 + (x2 - x1) * k, y1] : [x1, y1 + (y2 - y1) * k];
      const c2 = horizontal ? [x2 - (x2 - x1) * k, y2] : [x2, y2 - (y2 - y1) * k];
      const f = (n: number) => n.toFixed(1);
      next.push({ id: `${uid}-${i}`, d: `M${f(x1)} ${f(y1)}C${f(c1[0])} ${f(c1[1])} ${f(c2[0])} ${f(c2[1])} ${f(x2)} ${f(y2)}` });
    });
    setSize({ w: origin.width, h: origin.height });
    setPaths(next);
  }, [links, uid]);

  // No synchronous measure here: the observer's first callback runs right after layout,
  // so reading rects there never forces a reflow during hydration.
  useEffect(() => {
    const root = svg.current?.parentElement;
    if (!root) return;
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    root.querySelectorAll("[data-anchor]").forEach((el) => ro.observe(el));
    document.fonts?.ready.then(measure);
    return () => ro.disconnect();
  }, [measure]);

  // SMIL keeps running off screen; pause it when the lines cannot be seen.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => (entry.isIntersecting ? el.unpauseAnimations() : el.pauseAnimations()));
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <svg
      ref={svg}
      aria-hidden
      className={`pointer-events-none absolute inset-0 h-full w-full overflow-visible ${className}`}
      viewBox={size.w ? `0 0 ${size.w} ${size.h}` : undefined}
      data-connection-lines={paths.length}
    >
      {paths.map((p, i) => (
        <g key={p.id} className="animate-fade-in">
          <path id={p.id} d={p.d} className="dash-path" />
          {dots && !off && (
            <circle r={2} style={{ fill: "var(--cyan-400)", filter: "drop-shadow(0 0 4px rgba(34, 211, 238, 0.9))" }} data-dot>
              <animateMotion dur={`${4.2 + (i % 3) * 0.9}s`} begin={`${(i * 0.7).toFixed(1)}s`} repeatCount="indefinite" rotate="auto">
                <mpath href={`#${p.id}`} />
              </animateMotion>
            </circle>
          )}
        </g>
      ))}
    </svg>
  );
}
