import type { Transition, Variants } from "framer-motion";

// Motion tokens. Easing curves for entrances, springs for anything the pointer touches.
// Nothing bounces: every spring here is critically damped (bounce: 0).

/** Custom ease-out for page transitions and reveals; mirrors --ease-memory in globals.css. */
export const EASE_MEMORY = [0.22, 1, 0.36, 1] as const;

export const DURATION = { page: 0.4, reveal: 0.5 } as const;

/** Stagger between siblings on scroll reveal; mirrors --stagger. */
export const STAGGER = 0.06;

/** Pointer feedback: hover and press scale. */
export const SPRING_PRESS: Transition = { type: "spring", bounce: 0, visualDuration: 0.22 };

/** Larger surfaces that move or resize (panels, layout shifts). */
export const SPRING_LAYOUT: Transition = { type: "spring", bounce: 0, visualDuration: 0.35 };

/** Page transition: fade + 8px rise, 400ms. Under reduced motion Framer drops the rise, keeps the fade. */
export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: DURATION.page, ease: EASE_MEMORY } },
};

/** Parent of a scroll reveal: children enter 60ms apart. */
export const revealParent: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: STAGGER } },
};

export const revealChild: Variants = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: DURATION.reveal, ease: EASE_MEMORY } },
};
