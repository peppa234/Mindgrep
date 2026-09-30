import type { Metadata, Viewport } from "next";

import { AuroraBackground } from "@/components/visual/aurora-background";
import { MemoryTheme } from "@/components/visual/memory-theme";
import { SmoothScroll } from "@/components/visual/smooth-scroll";
import { fontVariables } from "@/lib/fonts";

import "lenis/dist/lenis.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "MemoryOS",
  description: "Ask and search everything you have written: notes, papers, and code.",
};

export const viewport: Viewport = {
  themeColor: "#06050D",
  colorScheme: "dark",
};

// The shell (nav, page width) lives in the route groups; this layer owns the canvas every
// route shares: fonts, the motion policy, the aurora and smooth scrolling.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fontVariables}>
      <body className="min-h-screen font-sans">
        <MemoryTheme>
          <AuroraBackground />
          <SmoothScroll />
          {children}
        </MemoryTheme>
      </body>
    </html>
  );
}
