"use client";

import { motion } from "framer-motion";
import { useState } from "react";

import { GlassPanel } from "@/components/visual/glass-panel";
import { revealChild, revealParent } from "@/lib/motion";

const ITEMS = ["repos", "notes", "papers", "concepts", "projects", "ideas"];

/** Replays the page-entrance recipe: fade + 8px rise, children 60ms apart. */
export function MotionDemo() {
  const [run, setRun] = useState(0);

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => setRun((n) => n + 1)}
        className="rounded-lg border border-line bg-glass px-3 py-1.5 text-sm text-mid transition-colors duration-300 hover:border-line-bright hover:text-hi"
      >
        Replay entrance
      </button>
      <motion.ul
        key={run}
        variants={revealParent}
        initial="hidden"
        animate="shown"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3"
      >
        {ITEMS.map((item, i) => (
          <motion.li key={item} variants={revealChild}>
            <GlassPanel padding="sm" glow={false}>
              <p className="font-mono text-xs text-mid">+{i * 60}ms</p>
              <p className="text-hi">{item}</p>
            </GlassPanel>
          </motion.li>
        ))}
      </motion.ul>
    </div>
  );
}
