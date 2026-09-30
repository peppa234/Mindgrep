import type { ReactNode } from "react";

/** A titled styleguide section with an anchor for the index. */
export function Section({
  id,
  index,
  title,
  lede,
  children,
}: {
  id: string;
  index: string;
  title: string;
  lede?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 border-t border-line pt-14">
      <div className="mb-8 grid gap-3 md:grid-cols-[10rem_1fr]">
        <span className="font-mono text-xs tracking-widest text-mid uppercase">{index}</span>
        <div className="space-y-2">
          <h2 id={`${id}-title`} className="text-h2">
            {title}
          </h2>
          {lede && <p className="max-w-2xl text-mid">{lede}</p>}
        </div>
      </div>
      <div className="md:pl-[10rem]">{children}</div>
    </section>
  );
}

/** Small uppercase label above a group of specimens. */
export function Label({ children }: { children: ReactNode }) {
  return <p className="mb-3 font-mono text-[11px] tracking-widest text-mid uppercase">{children}</p>;
}

/** A specimen caption: name on the first line, technical detail in mono below. */
export function Caption({ name, detail }: { name: ReactNode; detail?: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-sm text-hi">{name}</p>
      {detail && <p className="font-mono text-xs break-all text-mid">{detail}</p>}
    </div>
  );
}

/** A colour chip with its token name, CSS variable, raw value and Tailwind utility. */
export function Swatch({
  name,
  cssVar,
  value,
  utility,
  meaning,
  checker = false,
}: {
  name: string;
  cssVar: string;
  value: string;
  utility?: string;
  meaning?: string;
  checker?: boolean;
}) {
  return (
    <figure className="space-y-3">
      <div
        className={`h-20 rounded-xl border border-line ${checker ? "bg-[conic-gradient(var(--bg-elevated)_25%,var(--bg-void)_0_50%,var(--bg-elevated)_0_75%,var(--bg-void)_0)] bg-[length:16px_16px]" : ""}`}
      >
        <div className="h-full w-full rounded-[11px]" style={{ background: `var(${cssVar})` }} />
      </div>
      <figcaption className="space-y-0.5">
        <p className="text-sm text-hi">{name}</p>
        <p className="font-mono text-xs text-mid">{cssVar}</p>
        <p className="font-mono text-xs break-all text-mid">{value}</p>
        {utility && <p className="font-mono text-xs text-hi">{utility}</p>}
        {meaning && <p className="text-xs text-mid">{meaning}</p>}
      </figcaption>
    </figure>
  );
}
