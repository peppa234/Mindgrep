"use client";

import { motion } from "framer-motion";

import { pageVariants } from "@/lib/motion";

/** Page transition: every navigation fades the page in with an 8px rise. */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return (
    <motion.div variants={pageVariants} initial="hidden" animate="shown">
      {children}
    </motion.div>
  );
}
