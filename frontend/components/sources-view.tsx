"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { compact, relativeTime } from "@/lib/format";
import type { Source, Stats } from "@/lib/types";

const BUSY = new Set(["queued", "indexing"]);

const STATUS_STYLE: Record<Source["status"], string> = {
  idle: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  queued: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  indexing: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  ready: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  failed: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
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
    <div className="space-y-1">
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full bg-sky-500 transition-all ${fraction == null ? "w-1/3 animate-pulse" : ""}`}
          style={fraction != null ? { width: `${Math.max(3, fraction * 100)}%` } : undefined}
        />
      </div>
      <p className="text-xs text-zinc-500">{label}</p>
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
    <li className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900/50">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">{source.name}</h3>
        <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[source.status]}`}>
          {source.status}
        </span>
        <span className="truncate font-mono text-xs text-zinc-500" title={source.uri}>
          {source.kind === "git" ? "⎇ " : "📁 "}
          {source.uri}
        </span>
        <div className="ml-auto flex gap-1.5 text-xs">
          {pendingEmbeddings > 0 && !BUSY.has(source.status) && (
            <button
              disabled={busy}
              onClick={() => act(() => api.embed(source.id))}
              className="rounded-md border border-zinc-200 px-2 py-1 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              Embed {pendingEmbeddings} pending
            </button>
          )}
          <button
            disabled={busy || BUSY.has(source.status)}
            onClick={() => act(() => api.reindex(source.id))}
            className="rounded-md border border-zinc-200 px-2 py-1 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Re-index
          </button>
          {confirming ? (
            <>
              <button
                disabled={busy}
                onClick={() => act(() => api.deleteSource(source.id))}
                className="rounded-md bg-red-600 px-2 py-1 text-white hover:bg-red-700"
              >
                Delete index
              </button>
              <button onClick={() => setConfirming(false)} className="px-2 py-1 text-zinc-500">
                Cancel
              </button>
            </>
          ) : (
            <button
              disabled={busy || BUSY.has(source.status)}
              onClick={() => setConfirming(true)}
              className="rounded-md px-2 py-1 text-zinc-500 hover:text-red-600 disabled:opacity-50"
              title="Removes the index for this source. Your files are never touched."
            >
              Remove
            </button>
          )}
        </div>
      </div>

      <Progress source={source} />

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-500">
        <div>
          <dt className="inline">documents </dt>
          <dd className="inline font-medium text-zinc-800 dark:text-zinc-200">{compact(source.documents)}</dd>
          {Object.keys(source.documents_by_kind).length > 0 && (
            <span>
              {" "}
              ({Object.entries(source.documents_by_kind).map(([k, v]) => `${v} ${k}`).join(", ")})
            </span>
          )}
        </div>
        <div>
          <dt className="inline">chunks </dt>
          <dd className="inline font-medium text-zinc-800 dark:text-zinc-200">{compact(source.chunks)}</dd>
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
        <p className="rounded bg-red-50 px-2 py-1 font-mono text-xs text-red-700 dark:bg-red-500/10 dark:text-red-300">
          {error ?? source.error}
        </p>
      )}
      {stats?.warnings?.map((w) => (
        <p key={w} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          {w}
        </p>
      ))}
    </li>
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

  const field =
    "rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-amber-500 dark:border-zinc-700 dark:bg-zinc-900";
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex gap-1 text-sm">
        {(["local", "git"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(k)}
            className={`rounded-md px-3 py-1 ${kind === k ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-500"}`}
          >
            {k === "local" ? "Local folder" : "GitHub repository"}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          required
          value={uri}
          onChange={(e) => setUri(e.target.value)}
          placeholder={kind === "local" ? "notes   (a folder inside SOURCES_DIR)" : "https://github.com/you/repo"}
          className={`${field} min-w-64 flex-1 font-mono`}
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={suggested || "name"}
          className={`${field} w-44`}
        />
        <button
          disabled={saving || !uri}
          className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
        >
          {saving ? "Adding…" : "Add and index"}
        </button>
      </div>
      {kind === "local" && (
        <p className="text-xs text-zinc-500">
          Local folders are read from the directory mounted as <code className="font-mono">SOURCES_DIR</code> in{" "}
          <code className="font-mono">.env</code> (read-only). A folder holding many repositories is fine: each
          repo&apos;s git history is picked up.
        </p>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </form>
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Sources</h1>
        {stats && (
          <p className="text-xs text-zinc-500">
            {compact(stats.documents)} documents · {compact(stats.chunks)} chunks · {compact(stats.embedded)} embedded
            {stats.needs_ocr > 0 && ` · ${stats.needs_ocr} PDFs need OCR`}
          </p>
        )}
      </div>
      <AddSource onAdded={load} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-3">
        {sources?.map((source) => <SourceRow key={source.id} source={source} onChange={load} />)}
      </ul>
      {sources?.length === 0 && (
        <p className="py-8 text-center text-sm text-zinc-500">
          No sources yet. Add your notes folder, a folder of repositories, or a GitHub URL.
        </p>
      )}
    </div>
  );
}
