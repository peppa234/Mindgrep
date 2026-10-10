import { CodeBlock } from "@/components/code-block";
import { CitationChip } from "@/components/markdown";
import { ContrastTable } from "@/components/styleguide/contrast-table";
import { MotionDemo } from "@/components/styleguide/motion-demo";
import { MotionToggle } from "@/components/styleguide/motion-toggle";
import { Caption, Label, Section, Swatch } from "@/components/styleguide/parts";
import { AuroraBackground } from "@/components/visual/aurora-background";
import { ConnectionLines } from "@/components/visual/connection-lines";
import { GlassPanel } from "@/components/visual/glass-panel";
import { GlowButton } from "@/components/visual/glow-button";
import { MemoryOrb } from "@/components/visual/memory-orb";
import { NoiseOverlay } from "@/components/visual/noise-overlay";
import { OrbPoster } from "@/components/visual/orb-poster";

const SECTIONS = [
  ["color", "Colour"],
  ["contrast", "Contrast"],
  ["type", "Type"],
  ["glass", "GlassPanel"],
  ["button", "GlowButton"],
  ["effects", "Effects"],
  ["lines", "ConnectionLines"],
  ["orb", "MemoryOrb"],
  ["controls", "Controls"],
  ["code", "Code"],
  ["motion", "Motion"],
] as const;

const SURFACES = [
  { name: "Void", cssVar: "--bg-void", value: "#06050D", utility: "bg-void", meaning: "The canvas behind everything" },
  { name: "Base", cssVar: "--bg-base", value: "#0A0818", utility: "bg-ground", meaning: "Solid page areas" },
  {
    name: "Elevated",
    cssVar: "--bg-elevated",
    value: "#0F0C21",
    utility: "bg-elevated",
    meaning: "Solid raised areas: menus, sheets",
  },
  { name: "Glass", cssVar: "--surface-glass", value: "rgba(139,92,246,0.04)", utility: "bg-glass", checker: true },
  { name: "Glass border", cssVar: "--border-glass", value: "rgba(168,139,250,0.12)", utility: "border-line", checker: true },
  {
    name: "Bright border",
    cssVar: "--border-bright",
    value: "rgba(168,139,250,0.28)",
    utility: "border-line-bright",
    checker: true,
  },
];

const PALETTES = [
  {
    role: "Knowledge",
    rule: "Violet marks what MemoryOS knows: memories, concepts, the graph, the primary action.",
    alias: "text-knowledge · bg-knowledge = violet-400",
    swatches: [
      ["violet-300", "#C4B5FD"],
      ["violet-400", "#A78BFA"],
      ["violet-500", "#8B5CF6"],
      ["violet-600", "#7C3AED"],
      ["violet-900", "#2E1065"],
    ],
  },
  {
    role: "Live",
    rule: "Cyan marks what is happening now: streaming, indexing, the focused or active thing.",
    alias: "text-live · bg-live = cyan-400",
    swatches: [
      ["cyan-400", "#22D3EE"],
      ["cyan-500", "#06B6D4"],
    ],
  },
  {
    role: "Gap",
    rule: "Magenta marks what is missing: unimplemented ideas, gaps, failures. Text only on solid surfaces.",
    alias: "text-gap · bg-gap = magenta-500",
    swatches: [["magenta-500", "#D946EF"]],
  },
] as const;

const TEXT = [
  { token: "text-hi", cssVar: "--text-hi", value: "#EDEAFF", note: "Headings and body. AA everywhere." },
  {
    token: "text-mid",
    cssVar: "--text-mid",
    value: "#A5A0C4",
    note: "Secondary text. AA everywhere, 5.0:1 at the brightest aurora pixel.",
  },
  {
    token: "text-low",
    cssVar: "--text-low",
    value: "#6B6690",
    note: "Large text (24px+) and disabled only, on solid surfaces: 3.7:1 on bg-base fails AA for body text.",
  },
] as const;

const GLOWS = [
  {
    name: "glow-violet",
    cssVar: "--glow-violet",
    utility: "shadow-glow-violet",
    meaning: "Knowledge surfaces, primary action",
    spec: true,
  },
  { name: "glow-cyan", cssVar: "--glow-cyan", utility: "shadow-glow-cyan", meaning: "Live and active state", spec: true },
  {
    name: "glow-magenta",
    cssVar: "--glow-magenta",
    utility: "shadow-glow-magenta",
    meaning: "Gap cards on hover (added)",
    spec: false,
  },
] as const;

const MOTION_TOKENS = [
  ["Entrance ease", "--ease-memory", "cubic-bezier(0.22, 1, 0.36, 1)"],
  ["Page transition", "--duration-page", "400ms · fade + 8px rise"],
  ["Stagger", "--stagger", "60ms between siblings"],
  ["Press spring", "SPRING_PRESS", "spring · bounce 0 · 220ms · scale 1.02 / 0.98"],
  ["Layout spring", "SPRING_LAYOUT", "spring · bounce 0 · 350ms"],
  ["Aurora drift", "animate-aurora-a/b/c", "48s / 57s / 41s, sine-eased quarters, 60 steps each (~5 updates/s)"],
  ["Traveling dash", ".dash-path", "dashoffset -20 per 1.6s, linear"],
  ["Floating panel", "animate-float", "±3px, 7s ease-in-out, alternating"],
  ["Streaming word", "animate-word-in", "opacity 0 → 1, 420ms (kept under reduced motion)"],
  ["Glass hover", ".glass", "border + glow, 300ms ease"],
  ["Button sweep", ".glow-btn::after", "750ms --ease-memory"],
] as const;

export default function StyleguidePage() {
  return (
    // Full-width clip: the orb scene draws past its box and must not widen the page on phones.
    <div className="overflow-x-clip">
      <div className="mx-auto max-w-6xl px-6 pb-32">
        <header className="flex flex-col gap-10 pt-16 pb-14 md:pt-24">
          <p className="font-mono text-xs tracking-widest text-mid uppercase">MemoryOS · design system · foundation</p>
          <h1 className="max-w-4xl text-h1">
            Living <span className="text-violet-300">memory</span>, rendered in deep space.
          </h1>
          <p className="max-w-2xl text-lg text-mid">
            Every token, surface, state and effect of the redesign in one place. Tokens come from{" "}
            <code className="text-hi">app/globals.css</code>. Nothing here is mocked: the contrast figures are measured from
            the CSS the browser resolved.
          </p>
          <MotionToggle />
          <nav aria-label="Sections" className="flex flex-wrap gap-2">
            {SECTIONS.map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                className="rounded-full border border-line px-3 py-1 text-sm text-mid transition-colors duration-300 hover:border-line-bright hover:text-hi"
              >
                {label}
              </a>
            ))}
          </nav>
        </header>

        <div className="space-y-24">
          <Section
            id="color"
            index="01 · Colour"
            title="Colour carries meaning"
            lede="Violet is knowledge, cyan is live, magenta is a gap. A hue appears only when it says one of those three things. Everything else is the violet-biased dark and its text."
          >
            <Label>Surfaces</Label>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
              {SURFACES.map((s) => (
                <Swatch key={s.cssVar} {...s} />
              ))}
            </div>

            <div className="mt-14 grid gap-10 lg:grid-cols-3">
              {PALETTES.map((p) => (
                <div key={p.role}>
                  <Label>{p.role}</Label>
                  <p className="mb-2 text-sm text-mid">{p.rule}</p>
                  <p className="mb-5 font-mono text-xs text-hi">{p.alias}</p>
                  <div className="grid grid-cols-3 gap-4">
                    {p.swatches.map(([name, value]) => (
                      <Swatch key={name} name={name} cssVar={`--${name}`} value={value} utility={`*-${name}`} />
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-14">
              <Label>Text · on bg-base, the surface text-low is allowed on</Label>
              <div className="grid gap-4 md:grid-cols-3">
                {TEXT.map((t) => (
                  <div key={t.token} className="space-y-3 rounded-2xl border border-line bg-ground p-6">
                    <p className="text-2xl" style={{ color: `var(${t.cssVar})` }}>
                      Memory recalled
                    </p>
                    <Caption name={t.token} detail={`${t.cssVar} · ${t.value}`} />
                    <p className="text-sm text-mid">{t.note}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-14">
              <Label>Glows</Label>
              <div className="grid gap-8 sm:grid-cols-3">
                {GLOWS.map((g) => (
                  <figure key={g.name} className="space-y-5">
                    <div className="grid h-28 place-items-center">
                      <div
                        className="h-16 w-16 rounded-2xl border border-line-bright bg-elevated"
                        style={{ boxShadow: `var(${g.cssVar})` }}
                      />
                    </div>
                    <figcaption>
                      <Caption name={g.name} detail={`${g.cssVar} · ${g.utility}`} />
                      <p className="mt-1 text-xs text-mid">{g.meaning}</p>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </div>
          </Section>

          <Section
            id="contrast"
            index="02 · Contrast"
            title="WCAG AA, measured"
            lede="Each foreground is checked on every surface its usage rule allows, including the worst case: glass over all three aurora blobs at their unblurred peaks, a grid line and the brightest grain pixel."
          >
            <ContrastTable />
          </Section>

          <Section
            id="type"
            index="03 · Type"
            title="Three families, one voice each"
            lede="Sora for h1–h3 only. Geist for everything you read and click. JetBrains Mono for code, metrics and paths."
          >
            <div className="space-y-10">
              <div className="space-y-2">
                <Caption
                  name="h1 · Sora 600"
                  detail="text-h1 · clamp(2.5rem, 6vw, 5rem) · leading 0.95 · tracking -0.03em"
                />
                <p className="text-h1 font-display">Remember everything.</p>
              </div>
              <div className="space-y-2">
                <Caption
                  name="h2 · Sora 600"
                  detail="text-h2 · clamp(1.75rem, 3.2vw, 2.5rem) · leading 1.05 · tracking -0.025em"
                />
                <p className="text-h2 font-display">Your notes, papers and code, connected</p>
              </div>
              <div className="space-y-2">
                <Caption name="h3 · Sora 500" detail="text-h3 · 1.25rem · leading 1.25 · tracking -0.02em" />
                <p className="text-h3 font-display">Retrieval-augmented answers with citations</p>
              </div>
              <div className="grid gap-8 md:grid-cols-2">
                <div className="space-y-2">
                  <Caption name="Body · Geist" detail="font-sans · 16px / 1.5" />
                  <p className="text-hi">
                    MemoryOS indexes your repositories, Markdown notes and PDFs into one knowledge graph, then answers
                    questions with the exact passage it drew on.
                  </p>
                  <p className="text-sm text-mid">Secondary copy sits in text-mid at 14px: still 7.4:1 on glass.</p>
                </div>
                <div className="space-y-2">
                  <Caption name="Code · JetBrains Mono" detail="font-mono · 13px" />
                  <pre className="overflow-x-auto rounded-xl border border-line bg-ground p-4 font-mono text-[0.8125rem] leading-6 text-hi">
                    <code>{`backend/app/retrieval/hybrid.py:42
const recall = 0.913;  // 3,201 memories
fn rank(query: &str) -> Vec<Hit>`}</code>
                  </pre>
                </div>
              </div>
            </div>
          </Section>

          <Section
            id="glass"
            index="04 · GlassPanel"
            title="The one surface"
            lede="Translucent violet glass, backdrop blur, a lit top edge and a faint inner shadow. On hover, or when something inside has keyboard focus, the border brightens and the tone's glow appears over 300ms."
          >
            <Label>States</Label>
            <div className="grid gap-5 md:grid-cols-3">
              <GlassPanel>
                <Caption name="Rest" detail={"<GlassPanel>"} />
                <p className="mt-3 text-sm text-mid">Hover me: the border brightens and the violet glow appears.</p>
              </GlassPanel>
              <GlassPanel state="hover">
                <Caption name="Hover (pinned)" detail={'state="hover"'} />
                <p className="mt-3 text-sm text-mid">border-bright + glow-violet.</p>
              </GlassPanel>
              <GlassPanel>
                <Caption name="Focus within" detail=":has(:focus-visible)" />
                <p className="mt-3 text-sm text-mid">Tab to the link to see keyboard focus light the panel.</p>
                <a href="#glass" className="mt-3 inline-block text-sm text-knowledge underline underline-offset-4">
                  A focusable link
                </a>
              </GlassPanel>
              <GlassPanel glow={false}>
                <Caption name="Static" detail="glow={false}" />
                <p className="mt-3 text-sm text-mid">For containers and message bubbles that should not react.</p>
              </GlassPanel>
              <GlassPanel as="article" padding="lg">
                <Caption name="Padding lg, as article" detail={'as="article" padding="lg"'} />
                <p className="mt-3 text-sm text-mid">Padding: none, sm (16px), md (24px, default), lg (32px).</p>
              </GlassPanel>
              <GlassPanel padding="sm">
                <Caption name="Padding sm" detail={'padding="sm"'} />
              </GlassPanel>
            </div>

            <div className="mt-12">
              <Label>Tones</Label>
              <div className="grid gap-5 md:grid-cols-3">
                <GlassPanel tone="knowledge">
                  <p className="font-mono text-xs text-violet-300">knowledge</p>
                  <p className="mt-2 text-hi">How does hybrid retrieval weight BM25 against vectors?</p>
                  <p className="mt-3 text-sm text-mid">Violet tint: the user&apos;s own words, and memories.</p>
                </GlassPanel>
                <GlassPanel tone="live">
                  <p className="flex items-center gap-2 font-mono text-xs text-live">
                    <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-live shadow-glow-cyan" />
                    indexing
                  </p>
                  <p className="mt-2 text-hi">memoryos/backend · 214 of 380 files</p>
                  <p className="mt-3 text-sm text-mid">Cyan edge and glow: something happening now.</p>
                </GlassPanel>
                <GlassPanel tone="gap">
                  <p className="flex items-center gap-2 font-mono text-xs text-mid">
                    <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />
                    unimplemented idea
                  </p>
                  <p className="mt-2 text-hi">Re-rank search hits with the knowledge graph</p>
                  <p className="mt-3 text-sm text-mid">
                    Magenta edge, dot and glow. Text stays text-hi/mid: magenta text fails on glass over the aurora.
                  </p>
                </GlassPanel>
              </div>
              <div className="mt-5 grid gap-5 md:grid-cols-3">
                <GlassPanel tone="knowledge" state="hover" padding="sm">
                  <Caption name="knowledge · hover" detail="glow-violet" />
                </GlassPanel>
                <GlassPanel tone="live" state="hover" padding="sm">
                  <Caption name="live · hover" detail="glow-cyan" />
                </GlassPanel>
                <GlassPanel tone="gap" state="hover" padding="sm">
                  <Caption name="gap · hover" detail="glow-magenta" />
                </GlassPanel>
              </div>
            </div>
          </Section>

          <Section
            id="button"
            index="05 · GlowButton"
            title="One primary action"
            lede="Violet gradient and glow. A light sweep crosses it on hover or keyboard focus. Press feedback is a critically damped spring: 1.02 on hover, 0.98 on press, no overshoot."
          >
            <Label>States</Label>
            <div className="flex flex-wrap items-end gap-8">
              {(
                [
                  ["Rest", undefined],
                  ["Hover (pinned)", "hover"],
                  ["Pressed (pinned)", "pressed"],
                ] as const
              ).map(([label, state]) => (
                <div key={label} className="space-y-3">
                  <GlowButton state={state}>Ask your memory</GlowButton>
                  <p className="font-mono text-xs text-mid">{label}</p>
                </div>
              ))}
              <div className="space-y-3">
                <GlowButton disabled>Ask your memory</GlowButton>
                <p className="font-mono text-xs text-mid">Disabled</p>
              </div>
            </div>
            <p className="mt-4 text-sm text-mid">
              Focus: Tab to any button. The focus ring is violet-400, 2px, offset 2px, and focus also runs the sweep.
            </p>

            <div className="mt-12">
              <Label>Sizes and elements</Label>
              <div className="flex flex-wrap items-end gap-8">
                <div className="space-y-3">
                  <GlowButton size="md">Search</GlowButton>
                  <p className="font-mono text-xs text-mid">size=&quot;md&quot; · 40px</p>
                </div>
                <div className="space-y-3">
                  <GlowButton size="lg">Open your second brain</GlowButton>
                  <p className="font-mono text-xs text-mid">size=&quot;lg&quot; · 48px</p>
                </div>
                <div className="space-y-3">
                  <GlowButton href="#button" size="md">
                    As a link →
                  </GlowButton>
                  <p className="font-mono text-xs text-mid">href · renders next/link</p>
                </div>
              </div>
            </div>
          </Section>

          <Section
            id="effects"
            index="06 · Effects"
            title="The backdrop"
            lede="AuroraBackground is fixed behind this whole page. Below it is contained in a frame, with and without its grid, next to the grain that stops the gradients from banding."
          >
            <div className="grid gap-5 md:grid-cols-2">
              <figure className="space-y-3">
                <div className="relative isolate h-64 overflow-hidden rounded-2xl border border-line">
                  <AuroraBackground contained />
                </div>
                <figcaption>
                  <Caption
                    name="AuroraBackground"
                    detail="3 blobs (violet-600 12%, cyan-500 8%, violet-600 9%) · blur 120px · 64px grid · grain 3%"
                  />
                </figcaption>
              </figure>
              <figure className="space-y-3">
                <div className="relative isolate h-64 overflow-hidden rounded-2xl border border-line">
                  <AuroraBackground contained grid={false} />
                </div>
                <figcaption>
                  <Caption name="grid={false}" detail="Colour fields and grain only" />
                </figcaption>
              </figure>
              <figure className="space-y-3">
                <div
                  className="relative h-40 overflow-hidden rounded-2xl border border-line"
                  style={{ background: "linear-gradient(90deg, var(--bg-void), var(--violet-900))" }}
                >
                  <NoiseOverlay />
                </div>
                <figcaption>
                  <Caption name="NoiseOverlay at 3%" detail="The shipped setting: invisible as texture, breaks up banding" />
                </figcaption>
              </figure>
              <figure className="space-y-3">
                <div
                  className="relative h-40 overflow-hidden rounded-2xl border border-line"
                  style={{ background: "linear-gradient(90deg, var(--bg-void), var(--violet-900))" }}
                >
                  <NoiseOverlay opacity={0.3} />
                </div>
                <figcaption>
                  <Caption name="NoiseOverlay at 30%" detail="Exaggerated tenfold so the grain can be reviewed" />
                </figcaption>
              </figure>
            </div>
          </Section>

          <Section
            id="lines"
            index="07 · ConnectionLines"
            title="The signature motif"
            lede="Dashed beziers between any elements marked data-anchor, dashes travelling along them and cyan dots riding each path: data moving through the memory. Under reduced motion the lines stay and the dashes and dots stop."
          >
            <div className="relative grid grid-cols-3 gap-6 py-6 sm:gap-16">
              <div data-anchor="sg-a" className="relative z-10 col-start-2 row-start-1">
                <GlassPanel padding="sm" className="text-center text-sm">
                  memory
                </GlassPanel>
              </div>
              <div data-anchor="sg-b" className="relative z-10 col-start-1 row-start-2 mt-10">
                <GlassPanel padding="sm" className="text-center text-sm">
                  repos
                </GlassPanel>
              </div>
              <div data-anchor="sg-c" className="relative z-10 col-start-3 row-start-2 mt-10">
                <GlassPanel padding="sm" className="text-center text-sm">
                  notes
                </GlassPanel>
              </div>
              <ConnectionLines
                links={[
                  { from: "sg-a", to: "sg-b" },
                  { from: "sg-a", to: "sg-c" },
                  { from: "sg-b", to: "sg-c" },
                ]}
              />
            </div>
            <p className="mt-4 font-mono text-xs text-mid">
              {'<ConnectionLines links={[{ from: "a", to: "b" }]} />'} · stroke rgba(168,139,250,.25) · dasharray 4 6 · dots
              via animateMotion, paused off screen
            </p>
          </Section>

          <Section
            id="orb"
            index="08 · MemoryOrb"
            title="The one 3D object"
            lede="A distorted icosahedron with a wireframe cage, 800 particles in Keplerian orbit and bloom, lazy-loaded after the page is idle. The SVG poster renders first, and is all you see under reduced motion or without WebGL. The only other place 3D could appear is the graph; nowhere else."
          >
            <div className="grid gap-8 md:grid-cols-2">
              <figure className="space-y-3">
                <div className="mx-auto w-full max-w-sm">
                  <MemoryOrb />
                </div>
                <figcaption>
                  <Caption name="Live" detail="R3F · MeshDistortMaterial · Points + shader · Bloom(1.2, 0.2) · dpr [1, 2]" />
                </figcaption>
              </figure>
              <figure className="space-y-3">
                <div className="mx-auto aspect-square w-full max-w-sm">
                  <OrbPoster id="orb-sg" />
                </div>
                <figcaption>
                  <Caption name="Poster" detail="static SVG, server-rendered: first paint, reduced motion, no WebGL" />
                </figcaption>
              </figure>
            </div>
          </Section>

          <Section
            id="controls"
            index="09 · Controls"
            title="Everything else you click"
            lede="Secondary actions are ghost buttons; chips are neutral until active, when they turn cyan; errors carry a magenta accent while their text stays text-hi."
          >
            <div className="grid gap-10 md:grid-cols-2">
              <div className="space-y-3">
                <Label>Field</Label>
                <input
                  aria-label="Example field"
                  placeholder="Describe what you're looking for…"
                  className="field h-10 w-full px-3 text-sm"
                />
                <textarea
                  aria-label="Example textarea"
                  rows={2}
                  placeholder="Ask about your code, notes or papers…"
                  className="field block w-full resize-none px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-3">
                <Label>Ghost buttons</Label>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-ghost h-9 px-3 text-sm">
                    Re-index
                  </button>
                  <button type="button" data-tone="gap" className="btn-ghost h-9 px-3 text-sm">
                    Delete index
                  </button>
                  <button type="button" disabled className="btn-ghost h-9 px-3 text-sm">
                    Disabled
                  </button>
                </div>
                <Label>Segmented</Label>
                <div className="seg" role="group" aria-label="Example segmented control">
                  <button type="button" aria-pressed="true">
                    Auto
                  </button>
                  <button type="button" aria-pressed="false">
                    Hybrid
                  </button>
                  <button type="button" aria-pressed="false">
                    Vector
                  </button>
                </div>
              </div>
              <div className="space-y-3">
                <Label>Chips</Label>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip">neutral</span>
                  <button type="button" className="chip">
                    button
                  </button>
                  <button type="button" aria-pressed="true" className="chip">
                    active
                  </button>
                  <span className="chip" data-tone="gap">
                    missing word
                  </span>
                  <span className="kbd">Ctrl K</span>
                </div>
                <Label>Citations</Label>
                <p className="text-sm text-hi">
                  Rest <CitationChip n={1} active={false} /> and open <CitationChip n={2} active />
                </p>
              </div>
              <div className="space-y-3">
                <Label>Messages</Label>
                <p className="alert">The FastAPI backend is not reachable.</p>
                <p className="notice">Partial results. reranker unavailable</p>
                <p className="text-sm text-mid">
                  A{" "}
                  <a href="#controls" className="link">
                    link to a memory
                  </a>{" "}
                  inside secondary text.
                </p>
              </div>
            </div>
          </Section>

          <Section
            id="code"
            index="10 · Code"
            title="Highlighted, never decorated"
            lede="Syntax colours are muted tints, deliberately unlike the three semantic accents, on a solid surface where each passes AA. Search matches are marked in the live colour."
          >
            <div className="grid gap-5 lg:grid-cols-2">
              <CodeBlock
                language="python"
                startLine={10}
                terms={["token"]}
                content={`def issue_token(user_id: int, ttl: int = 3600) -> str:
    """Sign a short-lived access token."""
    payload = {"sub": str(user_id), "exp": now() + timedelta(seconds=ttl)}
    return jwt.encode(payload, SECRET, algorithm="HS256")  # HS256`}
              />
              <CodeBlock
                language="typescript"
                startLine={5}
                content={`export async function withRetry<T>(fn: () => Promise<T>, attempts = 5): Promise<T> {
  let delay = 200;
  for (let i = 0; i < attempts; i++) {
    try { return await fn(); } catch (err) { delay *= 2; }
  }
  throw new Error("unreachable");
}`}
              />
            </div>
          </Section>

          <Section
            id="motion"
            index="11 · Motion"
            title="Restraint is the brief"
            lede="Easing curves for entrances, springs for anything the pointer touches, and nothing bounces. With reduced motion (OS or the switch above) the drift, sweep and transforms stop and the fades remain."
          >
            <div className="grid gap-10 lg:grid-cols-2">
              <dl className="divide-y divide-line text-sm">
                {MOTION_TOKENS.map(([name, token, value]) => (
                  <div key={name} className="grid grid-cols-[9rem_1fr] gap-4 py-3">
                    <dt className="text-mid">{name}</dt>
                    <dd>
                      <span className="block font-mono text-xs text-hi">{token}</span>
                      <span className="block text-mid">{value}</span>
                    </dd>
                  </div>
                ))}
              </dl>
              <MotionDemo />
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
