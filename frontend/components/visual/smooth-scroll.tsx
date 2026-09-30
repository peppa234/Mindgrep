"use client";

import Lenis from "lenis";
import { useEffect } from "react";

import { useMotionOff } from "@/lib/stores/motion";

/**
 * Lenis smooth scrolling for the page. Off under reduced motion. Inner scroll areas opt
 * out with data-lenis-prevent so panels and code blocks scroll natively.
 */
export function SmoothScroll() {
  const off = useMotionOff();

  useEffect(() => {
    if (off) return;
    const lenis = new Lenis({ autoRaf: true, anchors: true, lerp: 0.12 });
    return () => lenis.destroy();
  }, [off]);

  return null;
}
