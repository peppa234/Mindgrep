import type {
  Conversation,
  ConversationDetail,
  DocumentDetail,
  Health,
  Idea,
  IdeaStatus,
  IdeaSummary,
  MessageOut,
  Neighbourhood,
  NodeDetail,
  NodeOut,
  ProjectSummary,
  SearchFilters,
  SearchMode,
  SearchResponse,
  Source,
  Stats,
} from "./types";

export const OFFLINE_MESSAGE = "The Mindgrep API is not responding. Check that the backend is running, then try again.";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** The backend could not be reached at all, as opposed to answering with an error. */
    public offline = false,
  ) {
    super(message);
  }
}

/** The text to show for anything a request can throw. */
export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

const HEALTH = "/health";

/** FastAPI answers /health in JSON whatever its state; the proxy alone does not. */
async function reachable(): Promise<boolean> {
  try {
    const response = await fetch(HEALTH, { cache: "no-store" });
    await response.json();
    return true;
  } catch {
    return false;
  }
}

/**
 * The error for a response that was not ok. When FastAPI is down, the Next proxy answers
 * for it with a bare "500 Internal Server Error" (and a gateway in front with 502–504),
 * which says nothing useful: those become one "not responding" error instead.
 */
export async function failure(response: Response, path: string): Promise<ApiError> {
  let message = `${response.status} ${response.statusText}`;
  let json = false;
  try {
    const body = await response.json();
    json = true;
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // not JSON; keep the status line
  }
  if (!json && response.status >= 500) {
    const gateway = response.status >= 502 && response.status <= 504;
    if (gateway || path === HEALTH || !(await reachable())) return new ApiError(response.status, OFFLINE_MESSAGE, true);
  }
  return new ApiError(response.status, message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, OFFLINE_MESSAGE, true);
  }
  if (!response.ok) throw await failure(response, path);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  search: (q: string, mode: SearchMode, filters: SearchFilters, k = 20) =>
    request<SearchResponse>("/api/v1/search", {
      method: "POST",
      body: JSON.stringify({ q, mode, k, filters }),
    }),
  sources: () => request<Source[]>("/api/v1/sources"),
  createSource: (body: { name: string; kind: "local" | "git"; uri: string }) =>
    request<Source>("/api/v1/sources", { method: "POST", body: JSON.stringify(body) }),
  reindex: (id: number, force = false) =>
    request<Source>(`/api/v1/sources/${id}/index${force ? "?force=true" : ""}`, { method: "POST" }),
  embed: (id: number) => request<{ job_id: string }>(`/api/v1/sources/${id}/embed`, { method: "POST" }),
  deleteSource: (id: number) => request<void>(`/api/v1/sources/${id}`, { method: "DELETE" }),
  stats: () => request<Stats>("/api/v1/stats"),
  document: (id: number) => request<DocumentDetail>(`/api/v1/documents/${id}`),
  health: () => request<Health>("/health"),

  conversations: () => request<Conversation[]>("/api/v1/conversations"),
  conversation: (id: number) => request<ConversationDetail>(`/api/v1/conversations/${id}`),
  deleteConversation: (id: number) => request<void>(`/api/v1/conversations/${id}`, { method: "DELETE" }),
  feedback: (messageId: number, rating: 1 | -1) =>
    request<MessageOut>(`/api/v1/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating }),
    }),
  projects: (uses?: string) =>
    request<ProjectSummary[]>(`/api/v1/graph/projects${uses ? `?uses=${encodeURIComponent(uses)}` : ""}`),
  node: (id: number) => request<NodeDetail>(`/api/v1/graph/nodes/${id}`),
  extract: (sourceId: number) =>
    request<{ job_id: string }>(`/api/v1/sources/${sourceId}/extract`, { method: "POST" }),
  neighbourhood: (id: number, depth = 1, kinds?: string[], limit = 50) => {
    const params = new URLSearchParams({ depth: String(depth), limit: String(limit) });
    for (const kind of kinds ?? []) params.append("kind", kind);
    return request<Neighbourhood>(`/api/v1/graph/nodes/${id}/neighbourhood?${params}`);
  },
  searchNodes: (q: string, kinds?: string[], limit = 12) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    for (const kind of kinds ?? []) params.append("kind", kind);
    return request<NodeOut[]>(`/api/v1/graph/nodes?${params}`);
  },

  ideas: (status: IdeaStatus | "all" = "all", sort: "oldest" | "newest" | "closest" = "oldest") =>
    request<Idea[]>(`/api/v1/ideas?status=${status}&sort=${sort}`),
  ideaSummary: () => request<IdeaSummary>("/api/v1/ideas/summary"),
  overrideIdea: (id: number, body: { status: IdeaStatus; project_id?: number | null; note?: string | null }) =>
    request<Idea>(`/api/v1/ideas/${id}/override`, { method: "PUT", body: JSON.stringify(body) }),
  clearIdeaOverride: (id: number) => request<Idea>(`/api/v1/ideas/${id}/override`, { method: "DELETE" }),
  refreshIdeas: () => request<{ job_id: string }>("/api/v1/ideas/refresh", { method: "POST" }),
};
