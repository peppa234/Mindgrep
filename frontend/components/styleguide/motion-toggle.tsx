"use client";

import { useReducedMotion } from "framer-motion";

import { useMotionPreference } from "@/lib/stores/motion";

/** Shows the OS reduced-motion setting and lets a reviewer preview the reduced experience. */
export function MotionToggle() {
  const system = useReducedMotion();
  const { forceReduced, setForceReduced } = useMotionPreference();
  const reduced = forceReduced || system === true;

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      <span className="flex items-center gap-2 text-mid">
        <span aria-hidden className={`h-2 w-2 rounded-full ${reduced ? "bg-low" : "bg-live shadow-glow-cyan"}`} />
        Motion {reduced ? "reduced" : "live"}
        <span className="font-mono text-xs">(OS: {system ? "reduce" : "no preference"})</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={forceReduced}
        onClick={() => setForceReduced(!forceReduced)}
        className="flex items-center gap-3 rounded-full border border-line bg-glass px-3 py-1.5 text-mid transition-colors duration-300 hover:border-line-bright hover:text-hi"
      >
        <span
          aria-hidden
          className={`relative h-4 w-7 rounded-full border transition-colors duration-300 ${
            forceReduced ? "border-cyan-400 bg-cyan-500/40" : "border-line-bright bg-void"
          }`}
        >
          <span
            className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-hi transition-[left] duration-300 ${forceReduced ? "left-3.5" : "left-0.5"}`}
          />
        </span>
        Preview reduced motion
      </button>
    </div>
  );
}
