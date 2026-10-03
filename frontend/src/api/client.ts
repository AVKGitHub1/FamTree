// Fetch wrapper: same-origin cookies, JSON bodies, the CSRF header on every
// state-changing request, and uniform errors.

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isStale(): boolean {
    return this.code === "stale_revision";
  }
}

let csrfToken = "";
let refreshCsrf: (() => Promise<void>) | null = null;

/** Called by the session layer whenever it learns a new token. */
export function setCsrfToken(token: string): void {
  csrfToken = token;
}

/** Lets the client recover once from an expired session's CSRF token. */
export function onCsrfRejected(refresh: () => Promise<void>): void {
  refreshCsrf = refresh;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function send(method: Method, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    const err = data?.error ?? {};
    return new ApiError(
      response.status,
      err.code ?? "error",
      err.message ?? "Something went wrong.",
      err.details ?? {},
    );
  } catch {
    const message =
      response.status >= 500
        ? "The server could not be reached. Try again in a moment."
        : "Something went wrong.";
    return new ApiError(response.status, "error", message);
  }
}

export async function requestRaw(method: Method, path: string, body?: unknown): Promise<Response> {
  let response: Response;
  try {
    response = await send(method, path, body);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check your connection.");
  }
  if (response.status === 403 && method !== "GET" && refreshCsrf) {
    const error = await toError(response.clone());
    if (error.code === "csrf") {
      await refreshCsrf();
      response = await send(method, path, body);
    }
  }
  if (!response.ok) throw await toError(response);
  return response;
}

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const response = await requestRaw(method, path, body);
  return (await response.json()) as T;
}
