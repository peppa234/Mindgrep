"use client";

import { MotionConfig } from "framer-motion";
import type { ReactNode } from "react";

import { useMotionPreference } from "@/lib/stores/motion";

/**
 * Applies the "living memory" system to a subtree: dark canvas, fonts, focus rings, and
 * one motion policy. Framer follows the OS reduced-motion setting, or the in-app override,
 * which also flips CSS effects through data-motion="reduce".
 */
export function MemoryTheme({ className = "", children }: { className?: string; children: ReactNode }) {
  const forced = useMotionPreference((s) => s.forceReduced);
  return (
    <MotionConfig reducedMotion={forced ? "always" : "user"}>
      <div data-motion={forced ? "reduce" : undefined} className={`memory-theme ${className}`}>
        {children}
      </div>
    </MotionConfig>
  );
}
