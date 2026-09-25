import type {
  DocumentDetail,
  Health,
  SearchFilters,
  SearchMode,
  SearchResponse,
  Source,
  Stats,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // not JSON; keep the status line
    }
    throw new ApiError(response.status, message);
  }
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
};
