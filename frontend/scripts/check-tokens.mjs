// Asserts app/globals.css declares every design token exactly as specified in the
// redesign brief (colour values compared numerically, so formatting may differ).
import { parseColor } from "../lib/contrast.ts";
import { readTokens } from "./read-tokens.mjs";

const SPEC = {
  "--bg-void": "#06050D",
  "--bg-base": "#0A0818",
  "--bg-elevated": "#0F0C21",
  "--surface-glass": "rgba(139,92,246,0.04)",
  "--border-glass": "rgba(168,139,250,0.12)",
  "--border-bright": "rgba(168,139,250,0.28)",
  "--violet-300": "#C4B5FD",
  "--violet-400": "#A78BFA",
  "--violet-500": "#8B5CF6",
  "--violet-600": "#7C3AED",
  "--violet-900": "#2E1065",
  "--cyan-400": "#22D3EE",
  "--cyan-500": "#06B6D4",
  "--magenta-500": "#D946EF",
  "--text-hi": "#EDEAFF",
  "--text-mid": "#A5A0C4",
  "--text-low": "#6B6690",
};
const SHADOWS = {
  "--glow-violet": "0 0 40px rgba(139,92,246,.35), 0 0 80px rgba(139,92,246,.15)",
  "--glow-cyan": "0 0 30px rgba(34,211,238,.30)",
};

const vars = readTokens(process.argv[2]);
const problems = [];
const same = (a, b) => ["r", "g", "b", "a"].every((k) => Math.abs(a[k] - b[k]) < 1e-6);
for (const [name, want] of Object.entries(SPEC)) {
  if (!(name in vars)) problems.push(`${name} missing`);
  else if (!same(parseColor(vars[name]), parseColor(want))) problems.push(`${name} is ${vars[name]}, spec ${want}`);
}
// Shadows: compare the numbers in order (lengths and channels), ignoring formatting.
const numbers = (s) => [...s.matchAll(/-?\d*\.?\d+/g)].map((m) => parseFloat(m[0]));
for (const [name, want] of Object.entries(SHADOWS)) {
  if (!(name in vars)) problems.push(`${name} missing`);
  else if (JSON.stringify(numbers(vars[name])) !== JSON.stringify(numbers(want))) problems.push(`${name} is ${vars[name]}, spec ${want}`);
}
for (const p of problems) console.log(`MISMATCH ${p}`);
console.log(`${Object.keys(SPEC).length + Object.keys(SHADOWS).length} spec tokens checked, ${problems.length} mismatched.`);
if (problems.length) {
  console.log("TOKENS DRIFTED");
  process.exitCode = 1;
} else console.log("TOKENS MATCH SPEC");
