import type { ChatDone, ChatSource } from "./types";

export interface ChatHandlers {
  onMeta?: (data: { conversation_id: number; user_message_id: number }) => void;
  onSources?: (sources: ChatSource[]) => void;
  onToken?: (text: string) => void;
  onDone?: (done: ChatDone) => void;
  onError?: (message: string) => void;
}

/**
 * POST /api/v1/chat and dispatch its Server-Sent Events. EventSource cannot send a body, so
 * this reads the response stream and splits it into events itself.
 */
export async function streamChat(
  body: { message: string; conversation_id?: number | null },
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // not JSON
    }
    handlers.onError?.(message);
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      dispatch(raw, handlers);
    }
  }
}

function dispatch(raw: string, handlers: ChatHandlers) {
  let name = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return;
  const payload = JSON.parse(data.join("\n"));
  switch (name) {
    case "meta":
      handlers.onMeta?.(payload);
      break;
    case "sources":
      handlers.onSources?.(payload.sources);
      break;
    case "token":
      handlers.onToken?.(payload.text);
      break;
    case "done":
      handlers.onDone?.(payload);
      break;
    case "error":
      handlers.onError?.(payload.message);
      break;
  }
}
