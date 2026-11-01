"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { CodeBlock } from "@/components/code-block";
import { Markdown } from "@/components/markdown";
import { GlassPanel } from "@/components/visual/glass-panel";
import { GlowButton } from "@/components/visual/glow-button";
import { api } from "@/lib/api";
import { lineRange, relativeTime } from "@/lib/format";
import { SPRING_LAYOUT, revealChild } from "@/lib/motion";
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
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active]);
  const where = source.page != null ? `p. ${source.page}` : lineRange(source.start_line, source.end_line);
  const href =
    source.document_id != null
      ? `/documents/${source.document_id}${source.chunk_id ? `#chunk-${source.chunk_id}` : ""}`
      : null;
  return (
    <article
      ref={ref}
      id={`source-${source.n}`}
      className={`space-y-2 rounded-xl border p-3 transition-[border-color,box-shadow] duration-300 ${
        active ? "border-cyan-400/50 shadow-glow-cyan" : "border-line"
      }`}
    >
      <div className="flex items-baseline gap-2 text-xs">
        <span
          className={`inline-flex h-[19px] min-w-[19px] items-center justify-center rounded-md border px-1 font-mono text-xs font-medium ${
            active ? "border-cyan-400/70 text-cyan-400" : "border-violet-400/40 text-violet-300"
          }`}
        >
          {source.n}
        </span>
        {href ? (
          <Link href={href} className="link truncate font-mono">
            {source.source_name}/{source.path}
          </Link>
        ) : (
          <span className="truncate font-mono text-mid">{source.path}</span>
        )}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-mid">
        {source.symbol && <span className="font-mono text-hi">{source.symbol}</span>}
        {where && <span className="font-mono">{where}</span>}
        {source.kind === "evidence" && <span className="chip py-0 text-xs">graph evidence</span>}
        {!cited && <span>not cited</span>}
        {source.modified_at && <span className="ml-auto">{relativeTime(source.modified_at)}</span>}
      </div>
      {source.content && (
        <CodeBlock
          content={source.content}
          language={source.language}
          startLine={source.doc_kind === "code" || source.kind === "evidence" ? source.start_line : null}
          maxLines={active ? 40 : 6}
        />
      )}
    </article>
  );
}

/** The slide-in source panel: every source behind the selected answer, the cited one open. */
function SourcePanel({
  turn,
  activeSource,
  onClose,
}: {
  turn: Turn | undefined;
  activeSource: number | null;
  onClose: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <motion.aside
      aria-labelledby="sources-title"
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={SPRING_LAYOUT}
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-line-bright bg-elevated/95 shadow-[-24px_0_80px_rgba(6,5,13,0.6)] backdrop-blur-xl sm:w-[32rem]"
    >
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <h2 id="sources-title" ref={headingRef} tabIndex={-1} className="text-h3 font-display outline-none">
          {turn?.abstained ? "Closest matches" : "Sources"}
        </h2>
        {turn && turn.sources.length > 0 && (
          <span className="font-mono text-xs text-mid">
            {turn.citations.length} of {turn.sources.length} cited
          </span>
        )}
        <button type="button" onClick={onClose} className="btn-ghost ml-auto h-8 px-2.5 text-xs" aria-label="Close sources">
          Close <span className="kbd">Esc</span>
        </button>
      </div>
      <div data-lenis-prevent className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {!turn || turn.sources.length === 0 ? (
          <p className="text-sm text-mid">{turn?.pending ? "Retrieving…" : "This answer has no sources."}</p>
        ) : (
          turn.sources.map((source) => (
            <SourceCard
              key={source.n}
              source={source}
              active={activeSource === source.n}
              cited={turn.abstained || Boolean(turn.pending) || turn.citations.includes(source.n)}
            />
          ))
        )}
      </div>
    </motion.aside>
  );
}

function Thumb({ up, active, onClick }: { up: boolean; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={up ? "Good answer" : "Bad answer"}
      className={`rounded-md p-1 transition-colors ${active ? "text-cyan-400" : "text-mid hover:text-hi"}`}
    >
      <svg
        viewBox="0 0 24 24"
        className={`h-4 w-4 ${up ? "" : "rotate-180"}`}
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth={1.8}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M7 11v9H4v-9h3zm0 0 4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7"
        />
      </svg>
    </button>
  );
}

function AssistantTurn({
  turn,
  activeSource,
  onCite,
  onSources,
  onFeedback,
}: {
  turn: Turn;
  activeSource: number | null;
  onCite: (n: number) => void;
  onSources: () => void;
  onFeedback: (rating: 1 | -1) => void;
}) {
  const valid = (n: number) => n >= 1 && n <= turn.sources.length;
  return (
    <GlassPanel glow={false} padding="none" className="space-y-3 px-5 py-4">
      <p className="flex items-center gap-2 font-mono text-xs tracking-widest text-mid uppercase">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-knowledge" />
        Mindgrep
        {turn.abstained && (
          <span className="flex items-center gap-1.5 normal-case tracking-normal text-hi">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />
            Not in your memory
          </span>
        )}
      </p>
      {turn.content ? (
        <Markdown text={turn.content} valid={valid} onCite={onCite} active={activeSource} streaming={turn.pending} />
      ) : turn.pending ? (
        <p className="flex items-center gap-2 text-sm text-mid" role="status">
          <span
            aria-hidden
            className="h-1.5 w-1.5 animate-pulse rounded-full bg-live shadow-glow-cyan motion-off:animate-none"
          />
          {turn.sources.length ? "Writing…" : "Searching your memory…"}
        </p>
      ) : null}
      {turn.error && (
        <p className="alert" role="alert">
          {turn.error}
        </p>
      )}
      {!turn.pending && !turn.error && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-mid">
          {turn.model === "graph" ? (
            <span
              className="chip border-violet-400/40 text-violet-300"
              title="Read off the knowledge graph: no language model involved"
            >
              knowledge graph
            </span>
          ) : turn.model ? (
            <span className="font-mono">{turn.model}</span>
          ) : null}
          {turn.sources.length > 0 && (
            <button type="button" onClick={onSources} className="chip">
              {turn.citations.length} of {turn.sources.length} sources cited
            </button>
          )}
          {turn.grounded === false && !turn.abstained && (
            <span className="flex items-center gap-1.5 text-hi" title="The answer does not cite any source">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-gap" />
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
    </GlassPanel>
  );
}

export function ChatView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const [conversationId, setConversationId] = useState<number | null>(params.get("c") ? Number(params.get("c")) : null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [selected, setSelected] = useState<number | null>(null); // index of the assistant turn shown in the panel
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [history, setHistory] = useState<Conversation[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const [shift, setShift] = useState(0);

  // On wide screens the conversation glides left so the open panel never covers the answer
  // it cites. Below that (the panel is full width on phones) it stays put.
  useEffect(() => {
    const PANEL = 512 + 24;
    const update = () => {
      const el = columnRef.current;
      if (!el || !panelOpen || window.innerWidth < 1024) return setShift(0);
      const rect = el.getBoundingClientRect();
      const left = rect.left - shift; // where the column sits when not shifted
      const overlap = left + rect.width - (window.innerWidth - PANEL);
      setShift(overlap > 0 ? -Math.min(overlap, Math.max(0, left - 24)) : 0);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [panelOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadHistory = useCallback(() => {
    api
      .conversations()
      .then(setHistory)
      .catch(() => setHistory([]));
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

  const openPanel = (index: number, n: number | null) => {
    if (!panelOpen && document.activeElement instanceof HTMLElement) returnFocus.current = document.activeElement;
    setSelected(index);
    setActiveSource(n);
    setPanelOpen(true);
  };
  const closePanel = useCallback(() => {
    setPanelOpen(false);
    returnFocus.current?.focus();
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
    setPanelOpen(false);
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
    <>
      <motion.div
        ref={columnRef}
        animate={{ x: shift }}
        transition={SPRING_LAYOUT}
        className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-3xl flex-col"
      >
        <div className="mb-6 flex items-center gap-2 text-sm">
          <button type="button" onClick={newChat} className="btn-ghost h-8 px-3">
            New chat
          </button>
          <button
            type="button"
            onClick={() => setShowHistory((s) => !s)}
            aria-expanded={showHistory}
            aria-controls="chat-history"
            className="btn-ghost h-8 px-3"
          >
            History {history && history.length > 0 ? <span className="font-mono text-xs">{history.length}</span> : null}
          </button>
        </div>

        <AnimatePresence initial={false}>
          {showHistory && (
            <motion.div
              id="chat-history"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="mb-6"
            >
              <GlassPanel
                glow={false}
                padding="none"
                as="ul"
                data-lenis-prevent
                className="max-h-72 divide-y divide-line overflow-y-auto text-sm"
              >
                {history?.length === 0 && <li className="px-4 py-3 text-mid">No conversations yet.</li>}
                {history?.map((c) => (
                  <li
                    key={c.id}
                    className={`group flex items-center gap-3 px-4 py-2 ${c.id === conversationId ? "bg-glass-knowledge" : ""}`}
                  >
                    <button
                      type="button"
                      aria-current={c.id === conversationId ? "true" : undefined}
                      className="min-w-0 flex-1 truncate text-left text-hi hover:text-violet-300"
                      onClick={() => {
                        setShowHistory(false);
                        router.replace(`${pathname}?c=${c.id}`, { scroll: false });
                      }}
                    >
                      {c.title}
                    </button>
                    <span className="shrink-0 text-xs text-mid">{relativeTime(c.updated_at)}</span>
                    <button
                      type="button"
                      onClick={() => removeConversation(c.id)}
                      className="shrink-0 text-xs text-mid opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:text-hi focus-visible:opacity-100"
                      aria-label={`Delete conversation “${c.title}”`}
                    >
                      delete
                    </button>
                  </li>
                ))}
              </GlassPanel>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex-1 space-y-5">
          {turns.length === 0 && (
            <div className="space-y-6 pt-10 text-center">
              <h1 className="text-h2">Ask your memory.</h1>
              <p className="mx-auto max-w-lg text-mid">
                Answers come from your notes, papers and code, with every claim cited. When the answer is not there, it says
                so.
              </p>
              <div className="mx-auto grid max-w-2xl gap-3 pt-2 text-left sm:grid-cols-2">
                {EXAMPLES.map((example) => (
                  <GlassPanel
                    key={example}
                    as="button"
                    type="button"
                    padding="sm"
                    onClick={() => ask(example)}
                    className="text-left text-sm text-mid transition-colors hover:text-hi"
                  >
                    {example}
                  </GlassPanel>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn, i) => (
            <motion.div key={i} variants={revealChild} initial="hidden" animate="shown">
              {turn.role === "user" ? (
                <div className="flex justify-end">
                  <GlassPanel
                    tone="knowledge"
                    glow={false}
                    padding="none"
                    className="max-w-[85%] rounded-br-md px-4 py-2.5 text-[0.9375rem] whitespace-pre-wrap text-hi"
                  >
                    {turn.content}
                  </GlassPanel>
                </div>
              ) : (
                <AssistantTurn
                  turn={turn}
                  activeSource={panelOpen && selected === i ? activeSource : null}
                  onCite={(n) => openPanel(i, n)}
                  onSources={() => openPanel(i, null)}
                  onFeedback={(rating) => feedback(i, rating)}
                />
              )}
            </motion.div>
          ))}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="alert mt-4" role="alert">
            {error}
          </p>
        )}

        <form
          onSubmit={submit}
          className="sticky bottom-0 mt-6 bg-gradient-to-t from-void via-void/90 to-transparent pt-6 pb-4"
        >
          <label htmlFor="chat-input" className="sr-only">
            Ask about your code, notes or papers
          </label>
          <div className="relative">
            <textarea
              id="chat-input"
              ref={inputRef}
              autoFocus
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask about your code, notes or papers…"
              className="field block w-full resize-none px-4 py-3 pr-28 text-[0.9375rem]"
            />
            <div className="absolute right-2.5 bottom-2.5">
              {streaming ? (
                <button type="button" onClick={() => abortRef.current?.abort()} className="btn-ghost h-8 px-3 text-sm">
                  Stop
                </button>
              ) : (
                <GlowButton type="submit" size="sm" disabled={!input.trim()}>
                  Ask
                </GlowButton>
              )}
            </div>
          </div>
          <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-mid">
            <span>
              <span className="kbd">Enter</span> to send
            </span>
            <span>
              <span className="kbd">Shift Enter</span> new line
            </span>
            <span>
              <span className="kbd">Ctrl K</span> focus
            </span>
          </p>
        </form>
      </motion.div>

      {/* Outside the column: a transformed ancestor would become the fixed panel's containing block. */}
      <AnimatePresence>
        {panelOpen && <SourcePanel key="sources" turn={panel} activeSource={activeSource} onClose={closePanel} />}
      </AnimatePresence>
    </>
  );
}
