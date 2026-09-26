"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { CodeBlock } from "@/components/code-block";
import { Markdown } from "@/components/markdown";
import { api } from "@/lib/api";
import { lineRange, relativeTime } from "@/lib/format";
import { streamChat } from "@/lib/sse";
import type { ChatSource, Conversation, Intent, MessageOut } from "@/lib/types";

interface Turn {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  citations: number[];
  abstained: boolean;
  intent?: Intent | null;
  grounded?: boolean;
  model?: string | null;
  degraded?: string[];
  feedback?: 1 | -1 | null;
  pending?: boolean;
  error?: string;
}

const EXAMPLES = [
  "Where did I implement JWT authentication?",
  "Which project used PostgreSQL?",
  "Show every project where I used FastAPI",
  "What was my original architecture for Student Portal?",
];

function fromMessage(m: MessageOut): Turn {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    sources: m.sources,
    citations: m.citations,
    abstained: m.abstained,
    intent: m.intent,
    grounded: m.trace.grounded ?? true,
    model: m.trace.model ?? null,
    degraded: m.trace.degraded ?? [],
    feedback: m.feedback,
  };
}

function SourceCard({ source, active, cited }: { source: ChatSource; active: boolean; cited: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active]);
  const where =
    source.page != null ? `p. ${source.page}` : lineRange(source.start_line, source.end_line);
  const href =
    source.document_id != null
      ? `/documents/${source.document_id}${source.chunk_id ? `#chunk-${source.chunk_id}` : ""}`
      : null;
  return (
    <div
      ref={ref}
      id={`source-${source.n}`}
      className={`space-y-1.5 rounded-lg border p-2.5 transition-colors ${
        active
          ? "border-amber-400 bg-amber-50/60 dark:border-amber-500/60 dark:bg-amber-500/5"
          : "border-zinc-200 dark:border-zinc-800"
      } ${cited ? "" : "opacity-70"}`}
    >
      <div className="flex items-baseline gap-2 text-xs">
        <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded bg-amber-100 px-1 font-mono text-[11px] font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
          {source.n}
        </span>
        {href ? (
          <Link href={href} className="truncate font-mono text-zinc-600 hover:text-amber-700 hover:underline dark:text-zinc-400 dark:hover:text-amber-400">
            {source.source_name}/{source.path}
          </Link>
        ) : (
          <span className="truncate font-mono text-zinc-600 dark:text-zinc-400">{source.path}</span>
        )}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-zinc-500">
        {source.symbol && <span className="font-mono">{source.symbol}</span>}
        {where && <span className="font-mono">{where}</span>}
        {source.kind === "evidence" && <span className="rounded border border-zinc-200 px-1 dark:border-zinc-700">graph evidence</span>}
        {source.modified_at && <span className="ml-auto">{relativeTime(source.modified_at)}</span>}
      </div>
      {source.content && (
        <CodeBlock
          content={source.content}
          startLine={source.doc_kind === "code" || source.kind === "evidence" ? source.start_line : null}
          maxLines={active ? 40 : 8}
        />
      )}
    </div>
  );
}

function Thumb({ up, active, onClick }: { up: boolean; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={up ? "Good answer" : "Bad answer"}
      className={`rounded p-1 transition-colors ${
        active ? "text-amber-600 dark:text-amber-400" : "text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
      }`}
    >
      <svg viewBox="0 0 24 24" className={`h-4 w-4 ${up ? "" : "rotate-180"}`} fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 11v9H4v-9h3zm0 0 4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7" />
      </svg>
    </button>
  );
}

function AssistantTurn({
  turn,
  selected,
  onCite,
  onSelect,
  onFeedback,
}: {
  turn: Turn;
  selected: boolean;
  onCite: (n: number) => void;
  onSelect: () => void;
  onFeedback: (rating: 1 | -1) => void;
}) {
  const valid = (n: number) => n >= 1 && n <= turn.sources.length;
  return (
    <div
      onClick={onSelect}
      className={`space-y-2 rounded-lg border-l-2 pl-4 ${selected ? "border-amber-400" : "border-transparent"}`}
    >
      {turn.abstained && (
        <p className="text-xs font-medium tracking-wide text-amber-700 uppercase dark:text-amber-400">Not in your memory</p>
      )}
      {turn.content ? (
        <Markdown text={turn.content} valid={valid} onCite={onCite} />
      ) : turn.pending ? (
        <p className="animate-pulse text-sm text-zinc-400">{turn.sources.length ? "Writing…" : "Searching…"}</p>
      ) : null}
      {turn.error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{turn.error}</p>
      )}
      {!turn.pending && !turn.error && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
          {turn.model === "graph" ? (
            <span className="rounded border border-emerald-300 px-1.5 text-emerald-700 dark:border-emerald-800 dark:text-emerald-400" title="Read off the knowledge graph: no language model involved">
              knowledge graph
            </span>
          ) : turn.model ? (
            <span className="font-mono">{turn.model}</span>
          ) : null}
          {turn.sources.length > 0 && (
            <span>
              {turn.citations.length} of {turn.sources.length} sources cited
            </span>
          )}
          {turn.grounded === false && !turn.abstained && (
            <span className="text-amber-600 dark:text-amber-400" title="The answer does not cite any source">
              uncited: check it against the sources
            </span>
          )}
          {turn.degraded && turn.degraded.length > 0 && <span title={turn.degraded.join("\n")}>degraded</span>}
          {turn.id != null && (
            <span className="ml-auto flex">
              <Thumb up active={turn.feedback === 1} onClick={() => onFeedback(1)} />
              <Thumb up={false} active={turn.feedback === -1} onClick={() => onFeedback(-1)} />
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [conversationId, setConversationId] = useState<number | null>(params.get("c") ? Number(params.get("c")) : null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [selected, setSelected] = useState<number | null>(null); // index of the assistant turn shown in the panel
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const [history, setHistory] = useState<Conversation[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(() => {
    api.conversations().then(setHistory).catch(() => setHistory([]));
  }, []);
  useEffect(loadHistory, [loadHistory]);

  // Open a conversation from the URL (?c=id), e.g. after a reload.
  useEffect(() => {
    const id = params.get("c") ? Number(params.get("c")) : null;
    // Already showing it (e.g. the URL just caught up with a conversation started here).
    if (id == null || (id === conversationId && turns.length > 0)) return;
    api
      .conversation(id)
      .then((c) => {
        setConversationId(c.id);
        const loaded = c.turns.map(fromMessage);
        setTurns(loaded);
        const last = loaded.map((t) => t.role).lastIndexOf("assistant");
        setSelected(last >= 0 ? last : null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prefill from ?q= (e.g. "Ask about this project" on a project page).
  useEffect(() => {
    const q = params.get("q");
    if (q) setInput(q);
  }, [params]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, turns[turns.length - 1]?.content.length]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const patchLast = (patch: (t: Turn) => Partial<Turn>) =>
    setTurns((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, ...patch(last) };
      return next;
    });

  async function ask(message: string) {
    if (!message.trim() || streaming) return;
    setError(null);
    setInput("");
    setStreaming(true);
    const assistantIndex = turns.length + 1;
    setTurns((t) => [
      ...t,
      { role: "user", content: message, sources: [], citations: [], abstained: false },
      { role: "assistant", content: "", sources: [], citations: [], abstained: false, pending: true },
    ]);
    setSelected(assistantIndex);
    setActiveSource(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(
        { message, conversation_id: conversationId },
        {
          onMeta: (meta) => {
            if (meta.conversation_id !== conversationId) {
              setConversationId(meta.conversation_id);
              router.replace(`${pathname}?c=${meta.conversation_id}`, { scroll: false });
            }
          },
          onSources: (sources) => patchLast(() => ({ sources })),
          onToken: (text) => patchLast((t) => ({ content: t.content + text })),
          onDone: (done) =>
            patchLast(() => ({
              id: done.message_id,
              pending: false,
              abstained: done.abstained,
              citations: done.citations,
              grounded: done.grounded,
              intent: done.intent,
              model: done.model,
              degraded: done.degraded,
            })),
          onError: (message) => patchLast(() => ({ pending: false, error: message })),
        },
        controller.signal,
      );
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      patchLast(() => ({ pending: false, error: aborted ? "Stopped." : e instanceof Error ? e.message : String(e) }));
    } finally {
      setStreaming(false);
      abortRef.current = null;
      loadHistory();
    }
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    ask(input);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function newChat() {
    abortRef.current?.abort();
    setConversationId(null);
    setTurns([]);
    setSelected(null);
    setActiveSource(null);
    router.replace(pathname, { scroll: false });
    inputRef.current?.focus();
  }

  async function feedback(index: number, rating: 1 | -1) {
    const turn = turns[index];
    if (turn.id == null) return;
    setTurns((t) => t.map((x, i) => (i === index ? { ...x, feedback: rating } : x)));
    try {
      await api.feedback(turn.id, rating);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function removeConversation(id: number) {
    await api.deleteConversation(id);
    if (id === conversationId) newChat();
    loadHistory();
  }

  const panel = selected != null ? turns[selected] : undefined;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="flex min-h-[calc(100vh-10rem)] flex-col">
        <div className="mb-4 flex items-center gap-2 text-sm">
          <button onClick={newChat} className="rounded-md border border-zinc-200 px-2.5 py-1 hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-900">
            New chat
          </button>
          <button
            onClick={() => setShowHistory((s) => !s)}
            className="rounded-md px-2.5 py-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            History {history && history.length > 0 ? `(${history.length})` : ""}
          </button>
        </div>

        {showHistory && (
          <ul className="mb-4 max-h-64 divide-y divide-zinc-100 overflow-y-auto rounded-lg border border-zinc-200 text-sm dark:divide-zinc-900 dark:border-zinc-800">
            {history?.length === 0 && <li className="px-3 py-2 text-zinc-500">No conversations yet.</li>}
            {history?.map((c) => (
              <li key={c.id} className={`group flex items-center gap-2 px-3 py-1.5 ${c.id === conversationId ? "bg-zinc-100 dark:bg-zinc-900" : ""}`}>
                <button
                  className="min-w-0 flex-1 truncate text-left hover:text-amber-700 dark:hover:text-amber-400"
                  onClick={() => {
                    setShowHistory(false);
                    router.replace(`${pathname}?c=${c.id}`, { scroll: false });
                  }}
                >
                  {c.title}
                </button>
                <span className="shrink-0 text-xs text-zinc-400">{relativeTime(c.updated_at)}</span>
                <button
                  onClick={() => removeConversation(c.id)}
                  className="shrink-0 text-xs text-zinc-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
                  title="Delete conversation"
                >
                  delete
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex-1 space-y-6">
          {turns.length === 0 && (
            <div className="space-y-4 pt-10 text-center">
              <p className="text-lg font-medium">Ask your memory.</p>
              <p className="text-sm text-zinc-500">
                Answers come from your notes, papers and code, with every claim cited. When the answer is not there, it says so.
              </p>
              <div className="mx-auto grid max-w-xl gap-2 pt-2 sm:grid-cols-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    onClick={() => ask(example)}
                    className="rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm text-zinc-600 hover:border-amber-400 hover:text-zinc-900 dark:border-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-100"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-zinc-900 px-4 py-2 text-[15px] whitespace-pre-wrap text-white dark:bg-zinc-100 dark:text-zinc-900">
                  {turn.content}
                </p>
              </div>
            ) : (
              <AssistantTurn
                key={i}
                turn={turn}
                selected={selected === i}
                onSelect={() => setSelected(i)}
                onCite={(n) => {
                  setSelected(i);
                  setActiveSource(n);
                }}
                onFeedback={(rating) => feedback(i, rating)}
              />
            ),
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>}

        <form onSubmit={submit} className="sticky bottom-0 mt-6 bg-zinc-50 pt-2 pb-4 dark:bg-zinc-950">
          <div className="relative">
            <textarea
              ref={inputRef}
              autoFocus
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask about your code, notes or papers…"
              className="w-full resize-none rounded-lg border border-zinc-300 bg-white px-4 py-3 pr-24 text-[15px] shadow-sm outline-none placeholder:text-zinc-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 dark:border-zinc-700 dark:bg-zinc-900"
            />
            {streaming ? (
              <button
                type="button"
                onClick={() => abortRef.current?.abort()}
                className="absolute right-2 bottom-3 rounded-md border border-zinc-300 px-3 py-1 text-sm dark:border-zinc-700"
              >
                Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="absolute right-2 bottom-3 rounded-md bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-30 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Ask
              </button>
            )}
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">Enter to send · Shift+Enter for a new line · Ctrl K to focus</p>
        </form>
      </section>

      <aside className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
        <h2 className="mb-2 text-xs font-medium tracking-wide text-zinc-500 uppercase">
          {panel?.abstained ? "Closest matches" : "Sources"}
        </h2>
        {!panel || panel.sources.length === 0 ? (
          <p className="text-sm text-zinc-500">
            {panel?.pending ? "Retrieving…" : "The sources behind an answer appear here. Click a citation to jump to it."}
          </p>
        ) : (
          <div className="space-y-2">
            {panel.sources.map((source) => (
              <SourceCard
                key={source.n}
                source={source}
                active={activeSource === source.n}
                cited={panel.abstained || panel.pending || panel.citations.includes(source.n)}
              />
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
