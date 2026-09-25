const units: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function lineRange(start: number | null, end: number | null): string {
  if (start == null) return "";
  return start === end ? `L${start}` : `L${start}–${end}`;
}

export function pageRange(meta: Record<string, unknown>): string {
  const start = meta.page_start as number | undefined;
  const end = meta.page_end as number | undefined;
  if (start == null) return "";
  return start === end ? `p. ${start}` : `pp. ${start}–${end}`;
}

export function compact(n: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(n);
}
