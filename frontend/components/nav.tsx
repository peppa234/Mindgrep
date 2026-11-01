"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Health } from "@/lib/types";

const links = [
  { href: "/chat", label: "Chat" },
  { href: "/search", label: "Search" },
  { href: "/projects", label: "Projects" },
  { href: "/ideas", label: "Ideas" },
  { href: "/graph", label: "Graph" },
  { href: "/sources", label: "Sources" },
];

/** The Mindgrep mark: a small lit sphere, the orb in miniature. */
export function Logo() {
  return (
    <span className="flex items-center gap-2.5 font-display text-[0.9375rem] font-medium tracking-tight text-hi">
      <span
        aria-hidden
        className="h-4 w-4 rounded-full shadow-glow-violet"
        style={{ background: "radial-gradient(circle at 35% 30%, var(--violet-300), var(--violet-600) 55%, var(--violet-900))" }}
      />
      Mindgrep
    </span>
  );
}

function ModelStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((h) => alive && (setHealth(h), setDown(false)))
        .catch(() => alive && setDown(true));
    load();
    const timer = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const models = health?.checks.models;
  // Live = cyan; a gap in the stack (offline, degraded) = magenta; unknown = neutral.
  const [dot, label, title] = down
    ? ["bg-gap", "API offline", "The FastAPI backend is not reachable"]
    : !models
      ? ["bg-low", "…", "Checking the model server"]
      : models.ok
        ? ["bg-live shadow-glow-cyan", models.embedding_model?.split("/").pop() ?? models.embedder, "Model server reachable"]
        : ["bg-gap", "lexical only", models.error ?? "Model server unreachable"];

  return (
    <span className="flex items-center gap-2 font-mono text-xs text-mid" title={title} role="status">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className="hidden sm:inline">{label}</span>
      <span className="sr-only sm:hidden">{label}</span>
    </span>
  );
}

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-void/70 backdrop-blur-xl">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-elevated focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 sm:gap-8 sm:px-6">
        <Link href="/" aria-label="Mindgrep home" className="shrink-0 rounded-md">
          <Logo />
        </Link>
        <nav aria-label="Main" className="-mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto px-1 py-1 text-sm">
          {links.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`relative shrink-0 rounded-lg px-3 py-1.5 transition-colors duration-200 ${
                  active ? "text-hi" : "text-mid hover:text-hi"
                }`}
              >
                {link.label}
                {active && (
                  <span
                    aria-hidden
                    className="absolute inset-x-3 bottom-0 h-px bg-live shadow-glow-cyan"
                  />
                )}
              </Link>
            );
          })}
        </nav>
        <ModelStatus />
      </div>
    </header>
  );
}
