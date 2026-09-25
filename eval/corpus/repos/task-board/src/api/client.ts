const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * fetch() that retries network failures and 5xx responses with exponential backoff
 * plus jitter: 250ms, 500ms, 1s, ... capped at 8s. 4xx responses are never retried.
 */
export async function fetchWithRetry(
  path: string,
  init: RequestInit = {},
  maxAttempts = 5,
): Promise<Response> {
  let attempt = 0;
  for (;;) {
    attempt += 1;
    try {
      const response = await fetch(`${BASE_URL}${path}`, init);
      if (response.status < 500 || attempt >= maxAttempts) {
        return response;
      }
    } catch (error) {
      if (attempt >= maxAttempts) throw error;
    }
    const backoff = Math.min(8000, 250 * 2 ** (attempt - 1));
    await sleep(backoff / 2 + Math.random() * (backoff / 2));
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetchWithRetry(path);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return (await response.json()) as T;
}
