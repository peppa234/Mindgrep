"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

import { revealChild, revealParent } from "@/lib/motion";

// The observed area reaches far above the viewport: a section the reader skipped past (End
// key, anchor link, fast fling) counts as seen, so it is never left invisible above them.
const VIEWPORT = { once: true, margin: "100000px 0px -80px 0px" } as const;

/** Scroll-triggered reveal: children fade up 8px, 60ms apart, once. */
export function Reveal({ children, className = "", as = "div" }: { children: ReactNode; className?: string; as?: "div" | "ul" | "ol" }) {
  const Tag = as === "ul" ? motion.ul : as === "ol" ? motion.ol : motion.div;
  return (
    <Tag variants={revealParent} initial="hidden" whileInView="shown" viewport={VIEWPORT} className={className}>
      {children}
    </Tag>
  );
}

export function RevealItem({ children, className = "", as = "div" }: { children: ReactNode; className?: string; as?: "div" | "li" }) {
  const Tag = as === "li" ? motion.li : motion.div;
  return (
    <Tag variants={revealChild} className={className}>
      {children}
    </Tag>
  );
}
