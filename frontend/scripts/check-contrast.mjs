// WCAG AA audit of the design tokens in app/globals.css, against the usage rules in
// lib/contrast.ts. Exits 1 on any failing pair. Usage: npm run check:contrast
import { OPEN_QUESTIONS, audit } from "../lib/contrast.ts";
import { readTokens } from "./read-tokens.mjs";

// Optional argument: another stylesheet to audit (used to prove the check can fail).
const vars = readTokens(process.argv[2]);

function print(rows) {
  const width = Math.max(...rows.map((r) => r.surface.length));
  let last = "";
  for (const row of rows) {
    if (row.label !== last) {
      console.log(`\n${row.label}  (needs ${row.min}:1 for ${row.use})`);
      last = row.label;
    }
    console.log(`  ${row.pass ? "pass" : "FAIL"}  ${row.surface.padEnd(width)}  ${row.ratio.toFixed(2)}:1`);
  }
}

const rows = audit(vars);
print(rows);
const failed = rows.filter((r) => !r.pass);

const open = audit(vars, OPEN_QUESTIONS, false);
console.log("\n── Open questions (reported, not gated) ──");
print(open);

console.log(`\n${rows.length} pairs audited, ${failed.length} failing.`);
if (failed.length) {
  console.log("CONTRAST FAIL");
  process.exitCode = 1;
} else {
  console.log("CONTRAST AA OK");
}
