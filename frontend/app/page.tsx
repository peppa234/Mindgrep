import type { Metadata } from "next";
import Link from "next/link";

import { FeatureGrid } from "@/components/landing/feature-grid";
import { HeroStage } from "@/components/landing/hero-stage";
import { Reveal, RevealItem } from "@/components/landing/reveal";
import { Logo } from "@/components/nav";
import { GlassPanel } from "@/components/visual/glass-panel";
import { GlowButton } from "@/components/visual/glow-button";

export const metadata: Metadata = {
  title: "MemoryOS · a second brain for developers",
  description:
    "MemoryOS indexes your repositories, Markdown notes and PDFs into one knowledge graph, then answers with the exact line it drew on.",
};

const STEPS = [
  { n: "01", title: "Index", body: "Repositories, notes and PDFs are parsed, chunked along the syntax tree and embedded, locally." },
  { n: "02", title: "Connect", body: "Manifests, imports, links and git history become a graph of projects, technologies and ideas." },
  { n: "03", title: "Recall", body: "Questions retrieve by meaning and by name, and answers cite the line they stand on." },
];

// Links here do not prefetch: prefetching makes the browser fetch and evaluate the app
// routes' code while the landing page is still becoming interactive (measured: a 227 ms long
// task for the chat route alone). Those pages load on click instead.
export default function LandingPage() {
  return (
    <>
      <header className="sticky top-0 z-30 border-b border-line bg-void/60 backdrop-blur-xl">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-elevated focus:px-3 focus:py-2 focus:text-sm"
        >
          Skip to content
        </a>
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Link prefetch={false} href="/" aria-label="MemoryOS home" className="rounded-md">
            <Logo />
          </Link>
          <nav aria-label="Product" className="hidden gap-1 text-sm md:flex">
            {[
              ["/search", "Search"],
              ["/graph", "Graph"],
              ["/ideas", "Ideas"],
              ["/sources", "Sources"],
            ].map(([href, label]) => (
              <Link prefetch={false} key={href} href={href} className="rounded-lg px-3 py-1.5 text-mid transition-colors hover:text-hi">
                {label}
              </Link>
            ))}
          </nav>
          <GlowButton prefetch={false} href="/chat" size="sm" className="ml-auto">
            Open MemoryOS
          </GlowButton>
        </div>
      </header>

      <main id="main">
        <section className="mx-auto grid max-w-6xl items-center gap-14 px-4 pt-14 pb-24 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-20">
          <div className="space-y-8">
            <p className="font-mono text-xs tracking-widest text-mid uppercase">A second brain for developers</p>
            <h1 className="text-h1">
              Everything you&apos;ve built, <span className="text-violet-300">remembered</span>.
            </h1>
            <p className="max-w-xl text-lg text-mid">
              MemoryOS indexes your repositories, Markdown notes and PDFs into one knowledge graph, then answers with the
              exact line it drew on. It runs on your machine; nothing leaves it.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <GlowButton prefetch={false} href="/chat" size="lg">
                Ask your memory
              </GlowButton>
              <Link prefetch={false} href="/graph" className="btn-ghost h-12 px-6 text-base">
                Explore the graph
              </Link>
            </div>
          </div>
          <HeroStage />
        </section>

        <section aria-labelledby="features-title" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
          <div className="mb-14 max-w-2xl space-y-3">
            <p className="font-mono text-xs tracking-widest text-mid uppercase">One memory, four ways in</p>
            <h2 id="features-title" className="text-h2">
              Ask it, search it, walk it, and find what is missing.
            </h2>
          </div>
          <FeatureGrid />
        </section>

        <section aria-labelledby="how-title" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
          <div className="mb-12 max-w-2xl space-y-3">
            <p className="font-mono text-xs tracking-widest text-mid uppercase">How it remembers</p>
            <h2 id="how-title" className="text-h2">
              From files to answers in three steps.
            </h2>
          </div>
          <Reveal as="ol" className="grid gap-5 md:grid-cols-3">
            {STEPS.map((s) => (
              <RevealItem as="li" key={s.n}>
                <GlassPanel glow={false} className="h-full space-y-3">
                  <p className="font-mono text-sm text-mid">{s.n}</p>
                  <h3 className="text-h3">{s.title}</h3>
                  <p className="text-mid">{s.body}</p>
                </GlassPanel>
              </RevealItem>
            ))}
          </Reveal>
        </section>

        <section className="mx-auto max-w-6xl px-4 pt-12 pb-28 sm:px-6">
          <Reveal>
            <RevealItem>
              <GlassPanel tone="knowledge" padding="lg" className="flex flex-col items-start gap-6 md:flex-row md:items-center md:justify-between md:p-12">
                <div className="max-w-xl space-y-3">
                  <h2 className="text-h2">Your code already knows the answer.</h2>
                  <p className="text-mid">Point MemoryOS at a folder of repositories and notes, and ask.</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <GlowButton prefetch={false} href="/sources" size="lg">
                    Add a source
                  </GlowButton>
                  <Link prefetch={false} href="/chat" className="btn-ghost h-12 px-6 text-base">
                    Open chat
                  </Link>
                </div>
              </GlassPanel>
            </RevealItem>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-8 font-mono text-xs text-mid sm:px-6">
          <span>MemoryOS · runs on your machine</span>
          <Link prefetch={false} href="/styleguide" className="hover:text-hi">
            Design system
          </Link>
          <Link prefetch={false} href="/sources" className="hover:text-hi">
            Sources
          </Link>
        </div>
      </footer>
    </>
  );
}
