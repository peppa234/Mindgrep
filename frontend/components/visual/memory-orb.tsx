"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { useMotionOff } from "@/lib/stores/motion";

import { OrbPoster } from "./orb-poster";

// three.js, drei and postprocessing load only here, after the page is interactive.
const OrbCanvas = dynamic(() => import("./orb-canvas"), { ssr: false, loading: () => null });

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

// First signs of a person at the page. Loading three.js (~250 KB of script to parse, then
// shader compilation) before any of these blocks the main thread while the page is still
// becoming interactive: measured as 470–2,780 ms of Lighthouse blocking time on idle load.
const INTENT = ["pointermove", "pointerdown", "wheel", "touchstart", "keydown", "scroll"] as const;

/**
 * The hero centerpiece. Server-renders a static poster; on the visitor's first interaction
 * it loads the WebGL orb and cross-fades to it. Reduced motion, or no WebGL, keeps the poster.
 */
export function MemoryOrb({ className = "" }: { className?: string }) {
  const off = useMotionOff();
  const [load, setLoad] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (off || !hasWebGL()) {
      setLoad(false);
      setReady(false);
      return;
    }
    const start = () => setLoad(true);
    for (const type of INTENT) window.addEventListener(type, start, { once: true, passive: true });
    return () => {
      for (const type of INTENT) window.removeEventListener(type, start);
    };
  }, [off]);

  const live = load && !off;
  return (
    <div className={`relative aspect-square ${className}`} data-orb={live && ready ? "canvas" : "poster"}>
      {/* The scene is drawn 18% beyond the layout box on each side: the particle ring and
          bloom extend past the sphere, and clipping them at the box edge reads as a cut. */}
      <div className="pointer-events-none absolute -inset-[18%]">
        <OrbPoster className={`absolute inset-0 transition-opacity duration-1000 ${live && ready ? "opacity-0" : "opacity-100"}`} />
        {live && (
          <OrbCanvas
            onReady={() => setReady(true)}
            className={`absolute inset-0 transition-opacity duration-1000 [mask-image:radial-gradient(closest-side,#000_82%,transparent_100%)] ${ready ? "opacity-100" : "opacity-0"}`}
          />
        )}
      </div>
    </div>
  );
}
