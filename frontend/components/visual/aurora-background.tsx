import type { CSSProperties } from "react";

import { NoiseOverlay } from "./noise-overlay";

const BLOBS: { animation: string; style: CSSProperties; color: string }[] = [
  { animation: "animate-aurora-a", style: { top: "-30vmax", left: "-20vmax" }, color: "var(--aurora-violet)" },
  { animation: "animate-aurora-b", style: { top: "-4vmax", right: "-34vmax" }, color: "var(--aurora-cyan)" },
  { animation: "animate-aurora-c", style: { bottom: "-46vmax", left: "8vmax" }, color: "var(--aurora-violet-deep)" },
];

/**
 * The deep-space backdrop: three huge, slowly drifting colour fields, a faint 64px grid
 * that fades out radially, and grain on top. Pure CSS; the drift stops under reduced motion.
 * Fixed to the viewport by default; `contained` fills the nearest positioned ancestor.
 */
export function AuroraBackground({
  grid = true,
  contained = false,
  className = "",
}: {
  grid?: boolean;
  contained?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={`${contained ? "absolute" : "fixed"} pointer-events-none inset-0 -z-10 overflow-hidden bg-void ${className}`}
    >
      {BLOBS.map((blob) => (
        <div
          key={blob.animation}
          className={`aurora-blob ${blob.animation} motion-off:animate-none`}
          style={{ ...blob.style, "--blob": blob.color } as CSSProperties}
        />
      ))}
      {grid && <div className="aurora-grid" />}
      <NoiseOverlay />
    </div>
  );
}
