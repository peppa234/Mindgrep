"use client";

import { useReducedMotion } from "framer-motion";
import { create } from "zustand";

// An in-app "reduce motion" override on top of the OS setting. Either one turns off the
// aurora drift, the button sweep, Framer transforms and (later) bloom, particles, parallax
// and traveling dashes. Opacity fades stay.
type MotionPreference = {
  forceReduced: boolean;
  setForceReduced: (value: boolean) => void;
};

export const useMotionPreference = create<MotionPreference>()((set) => ({
  forceReduced: false,
  setForceReduced: (forceReduced) => set({ forceReduced }),
}));

/** True when motion should be reduced, for effects driven from JavaScript (canvas, SVG). */
export function useMotionOff(): boolean {
  const system = useReducedMotion();
  const forced = useMotionPreference((s) => s.forceReduced);
  return forced || system === true;
}
