import { Geist, JetBrains_Mono, Sora } from "next/font/google";

// Self-hosted at build time with metric-matched fallbacks (no layout shift, no runtime
// request to Google). Each exposes a CSS variable that globals.css builds its stacks on.

/** Display: h1–h3 only. Geometric and precise; one variable file covers 500–600. */
export const display = Sora({ subsets: ["latin"], variable: "--font-display-face", display: "swap" });

/** Body and UI. */
export const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });

/** Code, metrics, file paths. Rarely above the fold, so not preloaded. */
export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
  preload: false,
});

export const fontVariables = `${display.variable} ${geist.variable} ${jetbrainsMono.variable}`;
