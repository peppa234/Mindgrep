"use client";

import { useEffect, useState } from "react";

import { type AuditRow, OPEN_QUESTIONS, type Vars, audit } from "@/lib/contrast";

/** Reads the tokens the browser actually resolved, so this table audits what renders. */
function liveVars(): Vars {
  const style = getComputedStyle(document.documentElement);
  return new Proxy({} as Vars, {
    get: (_, name) => (typeof name === "string" ? style.getPropertyValue(name).trim() || undefined : undefined),
  });
}

function Rows({ rows }: { rows: AuditRow[] }) {
  return (
    <>
      {rows.map((row, i) => {
        const first = i === 0 || rows[i - 1].label !== row.label;
        return (
          <tr key={`${row.label}-${row.surface}`} className={first ? "border-t border-line" : ""}>
            <th scope="row" className="py-2 pr-4 text-left align-top font-normal">
              {first && (
                <>
                  <span className="block text-hi">{row.label}</span>
                  <span className="block text-xs text-mid">{row.use}</span>
                </>
              )}
            </th>
            <td className="py-2 pr-4 align-top text-mid">{row.surface}</td>
            <td className="py-2 pr-4 text-right align-top font-mono tabular-nums">
              {row.ratio.toFixed(2)}:1
            </td>
            <td className="py-2 pr-4 text-right align-top font-mono text-mid tabular-nums">{row.min}:1</td>
            <td className="py-2 align-top">
              <span className="flex items-center gap-2">
                <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${row.pass ? "bg-line-bright" : "bg-gap"}`} />
                <span className={row.pass ? "text-hi" : "font-medium text-hi"}>{row.pass ? "Pass" : "Fail"}</span>
              </span>
            </td>
          </tr>
        );
      })}
    </>
  );
}

export function ContrastTable() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [open, setOpen] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const vars = liveVars();
      setRows(audit(vars));
      setOpen(audit(vars, OPEN_QUESTIONS, false));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  if (error) return <p className="text-hi">Could not read the tokens: {error}</p>;
  if (!rows || !open) return <p className="text-mid">Measuring…</p>;

  const failing = rows.filter((r) => !r.pass).length;
  const head = (
    <thead>
      <tr className="text-left font-mono text-xs tracking-widest text-mid uppercase">
        <th scope="col" className="pb-3 font-normal">Foreground and use</th>
        <th scope="col" className="pb-3 font-normal">Surface</th>
        <th scope="col" className="pb-3 text-right font-normal">Ratio</th>
        <th scope="col" className="pb-3 text-right font-normal">Needs</th>
        <th scope="col" className="pb-3 font-normal">AA</th>
      </tr>
    </thead>
  );

  return (
    <div className="space-y-10">
      <p className="text-sm text-mid">
        <span className="font-mono text-hi">{rows.length}</span> pairs measured from the live CSS,{" "}
        <span className="font-mono text-hi">{failing}</span> failing. The same matrix runs in{" "}
        <code className="text-hi">npm run check:contrast</code>.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">WCAG contrast of every token pair under its usage rule</caption>
          {head}
          <tbody>
            <Rows rows={rows} />
          </tbody>
        </table>
      </div>
      <div className="overflow-x-auto">
        <p className="mb-3 flex items-center gap-2 text-sm text-hi">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />
          Open question: measured, not gated
        </p>
        <table className="w-full min-w-[40rem] text-sm">
          <caption className="sr-only">Token uses the specified values cannot support</caption>
          {head}
          <tbody>
            <Rows rows={open} />
          </tbody>
        </table>
      </div>
    </div>
  );
}
