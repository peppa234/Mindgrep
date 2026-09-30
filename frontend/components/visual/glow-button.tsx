"use client";

import { type HTMLMotionProps, motion } from "framer-motion";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { SPRING_PRESS } from "@/lib/motion";
import { useMotionOff } from "@/lib/stores/motion";

const MotionLink = motion.create(Link);

const SIZE = {
  sm: "h-8 px-3.5 text-sm",
  md: "h-10 px-5 text-sm",
  lg: "h-12 px-7 text-base",
} as const;

type Common = {
  size?: keyof typeof SIZE;
  /** Pins a visual state on (for /styleguide). Interaction still works on top of it. */
  state?: "hover" | "pressed";
  className?: string;
  children: ReactNode;
};

type Controlled = "animate" | "initial" | "whileHover" | "whileTap" | "transition" | "children" | "className";

type ButtonProps = Common & { href?: undefined } & Omit<HTMLMotionProps<"button">, Controlled>;
type LinkProps = Common & { href: string } & Omit<ComponentProps<typeof MotionLink>, Controlled | "href">;

export type GlowButtonProps = ButtonProps | LinkProps;

/**
 * Primary call to action: violet gradient, violet glow, a light sweep on hover or focus,
 * and critically damped press feedback (1.02 hover, 0.98 press). Renders a Next.js <Link>
 * when given `href`. Under reduced motion there is no scale at all (Framer alone would still
 * jump to it) and CSS drops the sweep.
 */
export function GlowButton(props: GlowButtonProps) {
  const { size = "md", state, className = "", children, ...rest } = props;
  const disabled = "disabled" in rest && Boolean(rest.disabled);
  const still = useMotionOff();
  const pinned = state === "hover" ? 1.02 : state === "pressed" ? 0.98 : 1;
  const motionProps = {
    initial: false,
    animate: { scale: still ? 1 : pinned },
    whileHover: disabled || still ? undefined : { scale: 1.02 },
    whileTap: disabled || still ? undefined : { scale: 0.98 },
    transition: SPRING_PRESS,
    "data-state": state,
    className: `glow-btn ${SIZE[size]} ${className}`,
  } as const;

  if (rest.href !== undefined) {
    return (
      <MotionLink {...(rest as Omit<LinkProps, keyof Common>)} {...motionProps}>
        {children}
      </MotionLink>
    );
  }
  const { type = "button", ...buttonRest } = rest as Omit<ButtonProps, keyof Common>;
  return (
    <motion.button type={type} {...buttonRest} {...motionProps}>
      {children}
    </motion.button>
  );
}
