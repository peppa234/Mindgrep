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
  { href: "/sources", label: "Sources" },
];

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
  const [color, label, title] = down
    ? ["bg-red-500", "API offline", "The FastAPI backend is not reachable"]
    : !models
      ? ["bg-zinc-400", "…", ""]
      : models.ok
        ? ["bg-emerald-500", models.embedding_model?.split("/").pop() ?? models.embedder, "Model server reachable"]
        : ["bg-amber-500", "lexical only", models.error ?? "Model server unreachable"];

  return (
    <span className="flex items-center gap-2 text-xs text-zinc-500" title={title}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
        <Link href="/chat" className="font-semibold tracking-tight">
          Memory<span className="text-amber-600 dark:text-amber-400">OS</span>
        </Link>
        <nav className="flex gap-1 text-sm">
          {links.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-zinc-200/70 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          <ModelStatus />
        </div>
      </div>
    </header>
  );
}
