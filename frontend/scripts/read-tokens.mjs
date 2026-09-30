// Reads the custom properties declared in the first `:root { … }` block of app/globals.css.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const GLOBALS = fileURLToPath(new URL("../app/globals.css", import.meta.url));

export function readTokens(path = GLOBALS) {
  const css = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const start = css.search(/^:root\s*\{/m);
  if (start < 0) throw new Error(`No :root block in ${path}`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("\n}", start));
  const vars = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[m[1]] = m[2].trim();
  return vars;
}
