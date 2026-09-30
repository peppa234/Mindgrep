import type { PrismTheme } from "prism-react-renderer";

// Syntax highlighting maps Prism token types onto the muted --code-* palette in
// globals.css (audited by check:contrast). Styling lives in CSS classes, so the theme
// object Prism receives is empty.
export const EMPTY_THEME: PrismTheme = { plain: {}, styles: [] };

const CLASS_BY_TYPE: [RegExp, string][] = [
  [/^(comment|prolog|doctype|cdata)$/, "tok-comment"],
  [/^(string|char|attr-value|regex|template-string|url|inserted)$/, "tok-string"],
  [/^(number|boolean|constant|symbol|entity)$/, "tok-number"],
  [/^(keyword|atrule|important|selector|rule|deleted)$/, "tok-keyword"],
  [/^(class-name|builtin|tag|namespace|attr-name|property)$/, "tok-type"],
  [/^(function|function-variable|method|macro)$/, "tok-function"],
  [/^(punctuation|operator)$/, "tok-punct"],
];

export function tokenClass(types: string[]): string {
  for (const type of [...types].reverse()) {
    for (const [pattern, className] of CLASS_BY_TYPE) if (pattern.test(type)) return className;
  }
  return "";
}

// The indexer's language names (backend/app/services/ingestion/router.py) mapped onto the
// grammars prism-react-renderer bundles. C-family languages without a grammar borrow clike.
const PRISM_LANGUAGE: Record<string, string> = {
  python: "python",
  javascript: "javascript",
  typescript: "typescript",
  tsx: "tsx",
  go: "go",
  rust: "rust",
  c: "c",
  cpp: "cpp",
  kotlin: "kotlin",
  swift: "swift",
  sql: "sql",
  html: "markup",
  vue: "markup",
  svelte: "markup",
  css: "css",
  scss: "css",
  yaml: "yaml",
  json: "json",
  graphql: "graphql",
  markdown: "markdown",
  java: "clike",
  csharp: "clike",
  php: "clike",
  dart: "clike",
  scala: "clike",
};

export function prismLanguage(language: string | null | undefined): string | null {
  return language ? (PRISM_LANGUAGE[language.toLowerCase()] ?? null) : null;
}
