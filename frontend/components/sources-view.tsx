"use client";

import { motion } from "framer-motion";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { GlassPanel } from "@/components/visual/glass-panel";
import { GlowButton } from "@/components/visual/glow-button";
import { api } from "@/lib/api";
import { compact, relativeTime } from "@/lib/format";
import { revealChild, revealParent } from "@/lib/motion";
import type { Source, Stats } from "@/lib/types";

const BUSY = new Set(["queued", "indexing"]);

// Indexing is live (cyan); a ready index is knowledge (violet); a failure is a gap (magenta).
const STATUS_DOT: Record<Source["status"], string> = {
  idle: "border border-mid",
  queued: "bg-live",
  indexing: "bg-live shadow-glow-cyan animate-pulse motion-off:animate-none",
  ready: "bg-knowledge",
  failed: "bg-gap",
};

function Progress({ source }: { source: Source }) {
  const run = source.latest_run;
  if (!run || !BUSY.has(source.status)) return null;
  const s = run.stats;
  const parsing = run.stage === "parse" && s.files_total;
  const embedding = run.stage === "embed" && s.chunks_written;
  const fraction = parsing
    ? (s.files_done ?? 0) / (s.files_total || 1)
    : embedding
      ? (s.embedded ?? 0) / (s.chunks_written || 1)
      : null;
  const label = parsing
    ? `parsing ${s.files_done}/${s.files_total} files`
    : embedding
      ? `embedding ${s.embedded}/${s.chunks_written} chunks`
      : (run.stage ?? run.status);
  return (
    <div className="space-y-1.5">
      <div
        className="h-1 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={fraction == null ? undefined : Math.round(fraction * 100)}
      >
        <div
          className={`h-full rounded-full bg-live shadow-glow-cyan transition-[width] duration-500 ${
            fraction == null ? "w-1/3 animate-pulse motion-off:animate-none" : ""
          }`}
          style={fraction != null ? { width: `${Math.max(3, fraction * 100)}%` } : undefined}
        />
      </div>
      <p className="font-mono text-xs text-cyan-400">{label}</p>
    </div>
  );
}

function SourceRow({ source, onChange }: { source: Source; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = source.latest_run;
  const stats = run?.stats;
  const pendingEmbeddings = source.chunks - source.embedded;

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <GlassPanel as="article" tone={BUSY.has(source.status) ? "live" : source.status === "failed" ? "gap" : "neutral"} className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-h3">{source.name}</h2>
        <span className="chip text-hi">
          <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[source.status]}`} />
          {source.status}
        </span>
        <span className="flex min-w-0 items-center gap-1.5 font-mono text-xs text-mid" title={source.uri}>
          <span className="kbd">{source.kind === "git" ? "git" : "folder"}</span>
          <span className="truncate">{source.uri}</span>
        </span>
        <div className="ml-auto flex gap-1.5 text-xs">
          {pendingEmbeddings > 0 && !BUSY.has(source.status) && (
            <button type="button" disabled={busy} onClick={() => act(() => api.embed(source.id))} className="btn-ghost h-8 px-2.5">
              Embed {pendingEmbeddings} pending
            </button>
          )}
          <button
            type="button"
            disabled={busy || BUSY.has(source.status)}
            onClick={() => act(() => api.reindex(source.id))}
            className="btn-ghost h-8 px-2.5"
          >
            Re-index
          </button>
          {confirming ? (
            <>
              <button type="button" disabled={busy} onClick={() => act(() => api.deleteSource(source.id))} data-tone="gap" className="btn-ghost h-8 px-2.5">
                Delete index
              </button>
              <button type="button" onClick={() => setConfirming(false)} className="btn-ghost h-8 px-2.5">
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={busy || BUSY.has(source.status)}
              onClick={() => setConfirming(true)}
              className="btn-ghost h-8 px-2.5"
              title="Removes the index for this source. Your files are never touched."
            >
              Remove
            </button>
          )}
        </div>
      </div>

      <Progress source={source} />

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-mid">
        <div>
          <dt className="inline">documents </dt>
          <dd className="inline font-mono font-medium text-hi">{compact(source.documents)}</dd>
          {Object.keys(source.documents_by_kind).length > 0 && (
            <span>
              {" "}
              ({Object.entries(source.documents_by_kind).map(([k, v]) => `${v} ${k}`).join(", ")})
            </span>
          )}
        </div>
        <div>
          <dt className="inline">chunks </dt>
          <dd className="inline font-mono font-medium text-hi">{compact(source.chunks)}</dd>
          {pendingEmbeddings > 0 && <span> ({compact(source.embedded)} embedded)</span>}
        </div>
        {source.last_indexed_at && <div>indexed {relativeTime(source.last_indexed_at)}</div>}
        {source.last_commit && <div className="font-mono">@{source.last_commit.slice(0, 7)}</div>}
        {stats && run?.status === "succeeded" && (
          <div title={Object.entries(stats.skipped ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n")}>
            last run: {stats.indexed} changed, {stats.unchanged} unchanged
            {stats.deleted ? `, ${stats.deleted} deleted` : ""}
            {stats.needs_ocr ? `, ${stats.needs_ocr} need OCR` : ""}
            {stats.failed ? `, ${stats.failed} failed` : ""}
          </div>
        )}
      </dl>

      {(source.error || error) && (
        <p className="alert font-mono text-xs" role="alert">
          {error ?? source.error}
        </p>
      )}
      {stats?.warnings?.map((w) => (
        <p key={w} className="notice text-xs">
          {w}
        </p>
      ))}
    </GlassPanel>
  );
}

function AddSource({ onAdded }: { onAdded: () => void }) {
  const [kind, setKind] = useState<"local" | "git">("local");
  const [name, setName] = useState("");
  const [uri, setUri] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Suggest a name from the path or URL, until the user types one.
  const suggested = uri.replace(/\.git$/, "").split(/[/\\]/).filter(Boolean).pop()?.replace(/[^A-Za-z0-9._-]/g, "-") ?? "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createSource({ name: name || suggested, kind, uri });
      setName("");
      setUri("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <GlassPanel as="form" glow={false} onSubmit={submit} className="space-y-4" aria-label="Add a source">
      <div className="seg" role="group" aria-label="Source kind">
        {(["local", "git"] as const).map((k) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}>
            {k === "local" ? "Local folder" : "GitHub repository"}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <label htmlFor="source-uri" className="sr-only">
          {kind === "local" ? "Folder inside SOURCES_DIR" : "Repository URL"}
        </label>
        <input
          id="source-uri"
          required
          value={uri}
          onChange={(e) => setUri(e.target.value)}
          placeholder={kind === "local" ? "notes   (a folder inside SOURCES_DIR)" : "https://github.com/you/repo"}
          className="field h-10 min-w-64 flex-1 px-3 font-mono text-sm"
        />
        <label htmlFor="source-name" className="sr-only">
          Name
        </label>
        <input
          id="source-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={suggested || "name"}
          className="field h-10 w-44 px-3 text-sm"
        />
        <GlowButton type="submit" disabled={saving || !uri}>
          {saving ? "Adding…" : "Add and index"}
        </GlowButton>
      </div>
      {kind === "local" && (
        <p className="text-xs text-mid">
          Local folders are read from the directory mounted as <code className="font-mono text-hi">SOURCES_DIR</code> in{" "}
          <code className="font-mono text-hi">.env</code> (read-only). A folder holding many repositories is fine: each
          repo&apos;s git history is picked up.
        </p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </GlassPanel>
  );
}

export function SourcesView() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, st] = await Promise.all([api.sources(), api.stats()]);
      setSources(s);
      setStats(st);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is indexing.
  const active = sources?.some((s) => BUSY.has(s.status));
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, [active, load]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-h2">Sources</h1>
          <p className="text-mid">Folders and repositories Mindgrep reads. Your files are never modified.</p>
        </div>
        {stats && (
          <p className="font-mono text-xs text-mid">
            <span className="text-hi">{compact(stats.documents)}</span> documents · <span className="text-hi">{compact(stats.chunks)}</span>{" "}
            chunks · <span className="text-hi">{compact(stats.embedded)}</span> embedded
            {stats.needs_ocr > 0 && ` · ${stats.needs_ocr} PDFs need OCR`}
          </p>
        )}
      </div>
      <AddSource onAdded={load} />
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {sources && sources.length > 0 && (
        <motion.ul variants={revealParent} initial="hidden" animate="shown" className="space-y-4">
          {sources.map((source) => (
            <motion.li key={source.id} variants={revealChild}>
              <SourceRow source={source} onChange={load} />
            </motion.li>
          ))}
        </motion.ul>
      )}
      {sources?.length === 0 && (
        <p className="py-8 text-center text-sm text-mid">No sources yet. Add your notes folder, a folder of repositories, or a GitHub URL.</p>
      )}
    </div>
  );
}
