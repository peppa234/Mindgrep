import type { ComponentPropsWithoutRef, ElementType } from "react";

/** Tone carries meaning, never decoration: knowledge = violet, live = cyan, gap = magenta. */
export type GlassTone = "neutral" | "knowledge" | "live" | "gap";

const PADDING = { none: "", sm: "p-4", md: "p-6", lg: "p-8" } as const;

export type GlassPanelProps<T extends ElementType = "div"> = {
  as?: T;
  tone?: GlassTone;
  /** Border brightens and the tone's glow appears on hover or keyboard focus inside. */
  glow?: boolean;
  padding?: keyof typeof PADDING;
  /** Pins the hover look on (for /styleguide and controlled highlights). */
  state?: "hover";
} & Omit<ComponentPropsWithoutRef<T>, "as">;

/** The core surface: translucent violet glass with a lit top edge. Server-safe, CSS only. */
export function GlassPanel<T extends ElementType = "div">({
  as,
  tone = "neutral",
  glow = true,
  padding = "md",
  state,
  className,
  ...rest
}: GlassPanelProps<T>) {
  // Typed as a div for JSX checking: a bare ElementType would include the three.js
  // intrinsic elements R3F registers, whose props have no className.
  const Tag = (as ?? "div") as "div";
  return (
    <Tag
      data-tone={tone === "neutral" ? undefined : tone}
      data-glow={glow ? "" : undefined}
      data-state={state}
      className={`glass ${PADDING[padding]} ${className ?? ""}`}
      {...rest}
    />
  );
}
