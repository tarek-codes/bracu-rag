// Types mirroring the FastAPI schemas in backend/app/schemas.

export type UserRole = "user" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Citation {
  title: string;
  source_path?: string;
  page?: number | null;
  section?: string | null;
  snippet?: string;
  score?: number;
}

export interface Feedback {
  rating: 1 | -1;
  comment: string | null;
  user_id: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  feedback: Feedback | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSessionDetail extends Omit<ChatSession, "message_count"> {
  messages: ChatMessage[];
}

export type StreamEvent =
  | { event: "query_rewrite"; data: { rewritten_query: string } }
  | { event: "sources"; data: { citations: Citation[] } }
  | { event: "token"; data: { token: string } }
  | {
      event: "done";
      data: { session_id: string; message_id: string; full_text: string; fallback: boolean };
    }
  | { event: "error"; data: { message: string } };

/** Client side message state, which may still be streaming. */
export interface UiMessage {
  key: string;
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  feedback: Feedback | null;
  rewrittenQuery?: string;
  status: "waiting" | "streaming" | "done" | "error";
  fallback?: boolean;
  error?: string;
}

export interface DocumentItem {
  id: string;
  title: string;
  source: string;
  source_path: string | null;
  file_size: number | null;
  mime_type: string | null;
  chunks_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResult {
  documents: DocumentItem[];
  total: number;
}

export interface DocumentChunkItem {
  id: string;
  chunk_index: number;
  title: string | null;
  page: number | null;
  content: string;
  chunk_hash: string;
}

export interface DocumentDetail extends DocumentItem {
  content: string;
  chunks: DocumentChunkItem[];
}

export interface IngestionJob {
  id: string;
  source_type: string;
  status: "pending" | "processing" | "done" | "failed";
  stats: Record<string, number> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserListResult {
  users: User[];
  total: number;
}
