import type {
  ChatMessage,
  ChatSession,
  ChatSessionDetail,
  DocumentDetail,
  DocumentListResult,
  IngestionJob,
  TokenResponse,
  User,
  UserListResult,
} from "./types";

export const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let refreshPromise: Promise<boolean> | null = null;

/** Rotates the access token using the httpOnly refresh cookie. Deduplicated across callers. */
export function refreshSession(): Promise<boolean> {
  refreshPromise ??= fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
      return String((detail[0] as { msg: unknown }).msg).replace(/^Value error, /, "");
    }
  }
  return fallback;
}

/** fetch wrapper: sends cookies, retries once after a silent token refresh on 401. */
export async function apiFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return apiFetch(path, init, false);
  }
  return res;
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(res.status, detailMessage(body, "Something went wrong. Please try again."));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    json<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, full_name: string) =>
    json<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: full_name || null }),
    }),
  logout: () => json<{ message: string }>("/auth/logout", { method: "POST" }),
  me: () => json<User>("/auth/me"),

  listSessions: () => json<ChatSession[]>("/chat/sessions"),
  getSession: (id: string) => json<ChatSessionDetail>(`/chat/sessions/${id}`),
  renameSession: (id: string, title: string) =>
    json<ChatSession>(`/chat/sessions/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteSession: (id: string) => json<void>(`/chat/sessions/${id}`, { method: "DELETE" }),
  bulkDeleteSessions: (ids: string[]) =>
    json<{ deleted_count: number }>("/chat/sessions/bulk", {
      method: "DELETE",
      body: JSON.stringify({ ids }),
    }),
  clearSession: (id: string) => json<{ deleted_count: number }>(`/chat/sessions/${id}/clear`, { method: "POST" }),
  sendFeedback: (messageId: string, rating: 1 | -1, comment?: string) =>
    json<ChatMessage>(`/chat/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating, comment: comment || null }),
    }),

  // Admin Knowledge Base Endpoints
  listDocuments: (search?: string, skip = 0, limit = 50) => {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search?.trim()) params.set("search", search.trim());
    return json<DocumentListResult>(`/documents?${params.toString()}`);
  },
  getDocument: (id: string) => json<DocumentDetail>(`/documents/${id}`),
  deleteDocument: (id: string) => json<{ message: string }>(`/documents/${id}`, { method: "DELETE" }),
  bulkDeleteDocuments: (ids: string[]) =>
    json<{ deleted_count: number }>("/documents/bulk", {
      method: "DELETE",
      body: JSON.stringify({ ids }),
    }),
  reindexDocument: (id: string) => json<IngestionJob>(`/documents/${id}/reindex`, { method: "POST" }),
  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return json<IngestionJob>("/documents/upload", { method: "POST", body: formData });
  },
  ingestUrl: (url: string) =>
    json<IngestionJob>("/documents/url", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  listJobs: (limit = 20) => json<IngestionJob[]>(`/documents/jobs?limit=${limit}`),
  getJobStatus: (id: string) => json<IngestionJob>(`/documents/jobs/${id}`),

  // Admin User Management Endpoints
  listUsers: (skip = 0, limit = 50) => json<UserListResult>(`/users?skip=${skip}&limit=${limit}`),
  getUser: (id: string) => json<User>(`/users/${id}`),
  updateUserRole: (id: string, role: "user" | "admin") =>
    json<User>(`/users/${id}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  bulkDeleteUsers: (ids: string[]) =>
    json<{ deleted_count: number }>("/users/bulk", {
      method: "DELETE",
      body: JSON.stringify({ ids }),
    }),
};
