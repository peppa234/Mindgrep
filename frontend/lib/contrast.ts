// WCAG 2.x contrast for the design tokens. Shared by /styleguide (reading live CSS
// custom properties) and scripts/check-contrast.mjs (reading app/globals.css), so the
// page and the CI check audit the same matrix. Erasable TypeScript only: Node runs it
// directly with type stripping.

export type RGBA = { r: number; g: number; b: number; a: number };
export type Vars = Record<string, string>;

export const AA_TEXT = 4.5;
export const AA_LARGE = 3;

const clamp255 = (n: number) => Math.min(255, Math.max(0, n));

/** Resolve var() references against a token map, then parse hex, rgb(a) or color-mix(in srgb). */
export function parseColor(input: string, vars: Vars = {}): RGBA {
  const value = resolveVars(input.trim(), vars);
  const hex = /^#([0-9a-f]{3,8})$/i.exec(value);
  if (hex) {
    let h = hex[1];
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
    if (h.length !== 6 && h.length !== 8) throw new Error(`Bad hex colour: ${input}`);
    const n = (i: number) => parseInt(h.slice(i, i + 2), 16);
    return { r: n(0), g: n(2), b: n(4), a: h.length === 8 ? n(6) / 255 : 1 };
  }
  const rgb = /^rgba?\(([^)]+)\)$/i.exec(value);
  if (rgb) {
    const parts = rgb[1].split(/[\s,/]+/).filter(Boolean);
    const channel = (s: string) => (s.endsWith("%") ? (parseFloat(s) / 100) * 255 : parseFloat(s));
    const alpha = parts[3] === undefined ? 1 : parts[3].endsWith("%") ? parseFloat(parts[3]) / 100 : parseFloat(parts[3]);
    return { r: channel(parts[0]), g: channel(parts[1]), b: channel(parts[2]), a: alpha };
  }
  const mix = /^color-mix\(\s*in srgb\s*,(.+)\)$/i.exec(value);
  if (mix) {
    const [first, second] = splitTopLevel(mix[1]);
    const [colorA, pctA] = splitPercent(first);
    const [colorB, pctB] = splitPercent(second);
    const p = pctA ?? (pctB === undefined ? 0.5 : 1 - pctB);
    const a = parseColor(colorA, vars);
    const b = parseColor(colorB, vars);
    const lerp = (x: number, y: number) => x * p + y * (1 - p);
    return { r: lerp(a.r, b.r), g: lerp(a.g, b.g), b: lerp(a.b, b.b), a: lerp(a.a, b.a) };
  }
  throw new Error(`Unsupported colour: ${input}`);
}

function resolveVars(value: string, vars: Vars, depth = 0): string {
  if (depth > 10) throw new Error(`var() cycle in ${value}`);
  const next = value.replace(/var\(\s*(--[\w-]+)\s*(?:,[^()]*)?\)/g, (_, name: string) => {
    const found = vars[name];
    if (found === undefined) throw new Error(`Undefined token ${name}`);
    return found.trim();
  });
  return next === value ? value : resolveVars(next, vars, depth + 1);
}

function splitTopLevel(s: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")") depth--;
    else if (s[i] === "," && depth === 0) {
      out.push(s.slice(start, i).trim());
      start = i + 1;
    }
  }
  out.push(s.slice(start).trim());
  return out;
}

function splitPercent(part: string): [string, number | undefined] {
  const m = /^(.*\S)\s+([\d.]+)%$/.exec(part);
  return m ? [m[1], parseFloat(m[2]) / 100] : [part, undefined];
}

/** Paint `top` over `bottom` (source-over). */
export function over(top: RGBA, bottom: RGBA): RGBA {
  const a = top.a + bottom.a * (1 - top.a);
  if (a === 0) return { r: 0, g: 0, b: 0, a: 0 };
  const mixc = (t: number, b: number) => (t * top.a + b * bottom.a * (1 - top.a)) / a;
  return { r: mixc(top.r, bottom.r), g: mixc(top.g, bottom.g), b: mixc(top.b, bottom.b), a };
}

/** Flatten layers, listed bottom first, into one opaque colour. */
export function flatten(layers: RGBA[]): RGBA {
  const [first, ...rest] = layers;
  if (!first || first.a < 1) throw new Error("The bottom layer of a surface must be opaque");
  return rest.reduce((acc, layer) => over(layer, acc), first);
}

export function luminance({ r, g, b }: RGBA): number {
  const lin = (c: number) => {
    const s = clamp255(c) / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** Contrast of `fg` (composited onto the opaque `bg` if translucent) against `bg`. */
export function contrast(fg: RGBA, bg: RGBA): number {
  const text = fg.a < 1 ? over(fg, bg) : fg;
  const [hi, lo] = [luminance(text), luminance(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export const toHex = ({ r, g, b }: RGBA) =>
  "#" + [r, g, b].map((c) => Math.round(clamp255(c)).toString(16).padStart(2, "0")).join("").toUpperCase();

// ── The audit matrix ─────────────────────────────────────────────────────────

/** A surface is a stack of token names or literal colours, painted bottom first. */
export type Surface = { id: string; label: string; layers: string[] };

// Every aurora blob at its unblurred peak, overlapping, plus a grid line and the noise
// layer's brightest pixel (white at the overlay's 3%). No real pixel is this light: it is
// the worst case any glass panel can sit on, since the aurora is behind every page.
const AURORA_PEAK = ["--bg-void", "--aurora-violet", "--aurora-cyan", "--aurora-violet-deep", "--grid-line", "rgba(255, 255, 255, 0.03)"];

export const SURFACES: Surface[] = [
  { id: "void", label: "bg-void", layers: ["--bg-void"] },
  { id: "base", label: "bg-base", layers: ["--bg-base"] },
  { id: "elevated", label: "bg-elevated", layers: ["--bg-elevated"] },
  { id: "glass", label: "glass on bg-elevated", layers: ["--bg-elevated", "--surface-glass"] },
  { id: "aurora-glass", label: "glass on aurora peak", layers: [...AURORA_PEAK, "--surface-glass"] },
  { id: "aurora-knowledge", label: "knowledge glass on aurora peak", layers: [...AURORA_PEAK, "--surface-knowledge"] },
  { id: "aurora-live", label: "active chip on aurora peak", layers: [...AURORA_PEAK, "--surface-live"] },
  { id: "aurora-field", label: "field on aurora peak", layers: [...AURORA_PEAK, "--surface-field"] },
  { id: "code", label: "code surface", layers: ["--code-bg"] },
  { id: "code-mark", label: "search match in code", layers: ["--code-bg", "--code-mark"] },
];

/** Where each foreground may appear and the ratio that use needs. */
export type Pair = {
  fg: string;
  label: string;
  min: number;
  use: string;
  surfaces: string[];
};

const CODE = ["code", "code-mark"];
const ALL = SURFACES.map((s) => s.id).filter((id) => !CODE.includes(id));
const SOLID_BACKED = ["void", "base", "elevated", "glass"];
// Inside an active chip text turns cyan, so no other accent is ever drawn on that tint.
const NOT_LIVE = ALL.filter((id) => id !== "aurora-live");

export const PAIRS: Pair[] = [
  { fg: "--text-hi", label: "text-hi", min: AA_TEXT, use: "body and headings, anywhere", surfaces: ALL },
  { fg: "--text-mid", label: "text-mid", min: AA_TEXT, use: "secondary body text, anywhere", surfaces: ALL },
  { fg: "--violet-300", label: "violet-300", min: AA_TEXT, use: "knowledge text, anywhere but active chips", surfaces: NOT_LIVE },
  { fg: "--violet-400", label: "violet-400", min: AA_TEXT, use: "knowledge text and links, anywhere but active chips", surfaces: NOT_LIVE },
  { fg: "--cyan-400", label: "cyan-400", min: AA_TEXT, use: "live/active text, anywhere", surfaces: ALL },
  { fg: "--magenta-500", label: "magenta-500 text", min: AA_TEXT, use: "gap text, on solid surfaces only", surfaces: SOLID_BACKED },
  { fg: "--magenta-500", label: "magenta-500 accent", min: AA_LARGE, use: "non-text gap accents (lines, dots, borders), anywhere", surfaces: ALL },
  { fg: "--text-low", label: "text-low", min: AA_LARGE, use: "large text (24px+, 18.66px+ bold) and disabled, on solid surfaces only", surfaces: SOLID_BACKED },
  { fg: "--focus-ring", label: "focus ring", min: AA_LARGE, use: "non-text focus indicator (WCAG 1.4.11), anywhere", surfaces: ALL },
  { fg: "--code-text", label: "code text", min: AA_TEXT, use: "code identifiers", surfaces: CODE },
  { fg: "--code-keyword", label: "code keyword", min: AA_TEXT, use: "syntax: keywords", surfaces: CODE },
  { fg: "--code-string", label: "code string", min: AA_TEXT, use: "syntax: strings", surfaces: CODE },
  { fg: "--code-number", label: "code number", min: AA_TEXT, use: "syntax: numbers, constants", surfaces: CODE },
  { fg: "--code-type", label: "code type", min: AA_TEXT, use: "syntax: types, classes", surfaces: CODE },
  { fg: "--code-comment", label: "code comment", min: AA_TEXT, use: "syntax: comments", surfaces: CODE },
  { fg: "--code-punct", label: "code punctuation", min: AA_TEXT, use: "syntax: punctuation, operators", surfaces: CODE },
  { fg: "--code-gutter", label: "code line numbers", min: AA_TEXT, use: "line-number gutter", surfaces: ["code"] },
];

/** Measured and reported, never gated: uses the tokens as specified cannot support yet. */
export const OPEN_QUESTIONS: Pair[] = [
  { fg: "--text-low", label: "text-low at body size", min: AA_TEXT, use: "normal-size text (would need 4.5:1)", surfaces: ["base", "glass"] },
];

/** Button label on each point of the CTA fill, including under the hover sweep's peak. */
export const CTA_SURFACES: Surface[] = [
  { id: "cta-from", label: "CTA gradient start", layers: ["--cta-from"] },
  { id: "cta-to", label: "CTA gradient end", layers: ["--cta-to"] },
  { id: "cta-sweep", label: "CTA start under sweep peak", layers: ["--cta-from", "--cta-sweep"] },
];

export type AuditRow = { fg: string; label: string; use: string; surface: string; ratio: number; min: number; pass: boolean };

export function audit(vars: Vars, pairs: Pair[] = PAIRS, withCta = true): AuditRow[] {
  const color = (token: string) => parseColor(token.startsWith("--") ? `var(${token})` : token, vars);
  const surfaceColor = (s: Surface) => flatten(s.layers.map(color));
  const rows: AuditRow[] = [];
  for (const pair of pairs) {
    for (const surface of SURFACES.filter((s) => pair.surfaces.includes(s.id))) {
      const ratio = contrast(color(pair.fg), surfaceColor(surface));
      rows.push({ fg: pair.fg, label: pair.label, use: pair.use, surface: surface.label, ratio, min: pair.min, pass: ratio >= pair.min });
    }
  }
  for (const surface of withCta ? CTA_SURFACES : []) {
    const ratio = contrast(color("--text-hi"), surfaceColor(surface));
    rows.push({ fg: "--text-hi", label: "CTA label", use: "button text", surface: surface.label, ratio, min: AA_TEXT, pass: ratio >= AA_TEXT });
  }
  return rows;
}
