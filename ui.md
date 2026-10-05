# UI Guide: BRAC University Information Chatbot

Keep the UI minimal, responsive, and clean, in the style of modern conversational platforms like the Claude web app. Build only what the features need: fast interactions, crisp typography, and uncluttered views.

Stack: Next.js 16.3.7 (App Router), Bun 1.4.2, TypeScript (strict mode, no `any`), Tailwind CSS v4, shadcn/ui, `lucide-react`. See `techstack.md`.

---

## 1. Design Principles

- **Institutional Identity**: Deep BRAC University navy blue accent, clean neutral backgrounds, high legibility, and zero visual clutter.
- **Content First**: Conversation takes center stage; sidebar and navigation remain unobtrusive.
- **Palette**: Neutral surfaces with a single deep blue accent in both light and dark modes (respecting system preference with a manual toggle).
- **Typography**: **Poppins** for headings, brand title, and primary buttons; **Satoshi** for body text, chat dialogue, and inputs. Readable 16px base size for messages.
- **Geometry**: Subtle rounded corners (`rounded-xl` for cards and input boxes), crisp 1px borders instead of heavy drop shadows.
- **Responsive**: Seamless on mobile, tablet, and desktop. The sidebar collapses into a slide-over sheet drawer on mobile viewports.
- **Accessibility**: Semantic HTML, visible focus rings, ARIA labels, complete keyboard navigation, and high contrast ratios.
- **Strict Copy Constraint**: Institutional standard: never use em dashes anywhere in UI text, tooltips, placeholders, or error messages. Use colons, commas, semicolons, parentheses, or regular hyphens instead.

### Color Tokens

Define these tokens as CSS variables in `globals.css` and reference them via Tailwind CSS v4:

| Token | Light Mode | Dark Mode | Notes |
|---|---|---|---|
| `--color-background` | `#fafbfc` | `#14171c` | Page root background |
| `--color-surface` | `#f1f3f6` | `#1b1f26` | Sidebar, cards, secondary buttons |
| `--color-surface-hover` | `#e7ebf0` | `#232832` | Hovered items and chips |
| `--color-border` | `#e2e6ec` | `#2c323c` | 1px borders and dividers |
| `--color-text` | `#16191f` | `#e8ebf0` | Primary content and headings |
| `--color-text-muted` | `#646b78` | `#98a0ad` | Secondary timestamps, chips, captions |
| `--color-accent` | `#0b3b8f` | `#6f9bf0` | BRACU Navy Blue, interactive elements |
| `--color-accent-hover` | `#082c6c` | `#8bb0f5` | Accent hover state |
| `--color-accent-fg` | `#ffffff` | `#0b1020` | Text on accent background |
| `--color-error` | `#dc2626` | `#f87171` | Validation errors, failed status |
| `--color-success` | `#16a34a` | `#4ade80` | Success banners, completed status |

Use the accent color specifically for primary CTA buttons, links, active sidebar links, send buttons, and focus rings.

### Typography & Tailwind CSS v4 Theme Configuration

Tailwind CSS v4 uses CSS `@theme` declarations instead of `tailwind.config.js`:

```css
@import "tailwindcss";

@theme {
  --font-heading: var(--font-poppins), system-ui, sans-serif;
  --font-sans: var(--font-satoshi), system-ui, sans-serif;
  --color-primary: var(--color-accent);
  --color-primary-foreground: var(--color-accent-fg);
}
```

1. **Poppins**: Loaded via `next/font/google` (weights 500 and 600) with CSS variable `--font-poppins`.
2. **Satoshi**: Loaded via `next/font/local` using `.woff2` font files placed in `app/fonts/` (weights 400, 500, 700) with CSS variable `--font-satoshi`. Fallback stack: `system-ui, sans-serif`.

---

## 2. Pages & Route Architecture

| Route | Access | Purpose |
|---|---|---|
| `/` | Public / All | Root redirect: logged-in users go to `/chat`, admins go to `/admin/knowledge`, visitors can start guest chat or log in |
| `/login` | Public | Single authentication entry point for students, faculty, and admins |
| `/register` | Public | Self-service registration for student accounts (`role="user"`) |
| `/chat` | User / Admin / Guest | Main chat workspace, auto-creates session on initial query |
| `/chat/[id]` | User / Admin | Persistent session workspace with message history and citations |
| `/admin/knowledge` | Admin Only | Knowledge base management: upload files, crawl URLs, re-index, delete |
| `/admin/users` | Admin Only | User administration: inspect accounts, search users, update user roles |

---

## 3. Authentication & Route Protection

### One Login for All Roles

There is a single `/login` page:
- Form fields: Institutional Email (`email`), Password (`password`).
- On successful submission, the backend issues secure `access_token` and `refresh_token` httpOnly cookies, and returns user data.
- Read `role` from the response (or `GET /api/v1/auth/me`):
  - `role === "admin"` redirects to `/admin/knowledge`.
  - `role === "user"` redirects to `/chat`.
- If an authorized `returnUrl` query parameter is present, redirect to that destination instead.
- Logged-in users navigating to `/login` or `/register` are automatically forwarded to their role home page.
- Generic error messaging on invalid credentials: *"Invalid email or password"*. Never reveal whether the email exists or belongs to an admin.

### Registration

- Self-service registration at `/register` always creates regular accounts with `role="user"`.
- Fields: Full Name (`full_name`), BRACU Email (`email`), Password (`password`), Confirm Password.
- Password requirements: minimum 8 characters.
- Admin accounts cannot be self-registered; they are created via backend CLI (`python -m app.cli create-admin`) or promoted by existing administrators in `/admin/users`.

### Next.js Route Protection (`proxy.ts`)

Next.js 16 uses `proxy.ts` to inspect incoming cookies:
- Protect `/admin/*` routes: verify token validity and ensure `role === "admin"`. If not an admin, redirect to `/chat`.
- Protect `/chat/[id]` routes for authenticated users.
- The backend remains the source of truth, returning HTTP 401/403 on invalid requests.

---

## 4. Chat Workspace (`/chat` and `/chat/[id]`)

### Layout Grid

1. **Collapsible Left Sidebar** (width: 260px desktop, drawer sheet on mobile):
   - **Header**: App logo with BRACU monogram, app title, and "New Chat" button (`Cmd/Ctrl + K` shortcut).
   - **Session List**: Chronological grouping of conversations (*Today*, *Yesterday*, *Previous 7 Days*, *Older*).
   - **Session Item Actions**: Three-dot context menu for Rename, Clear Messages, and Delete (with confirmation dialog).
   - **Footer (User Card)**: User name, role badge (`Admin` or `Student`), Theme Toggle, Admin Dashboard link (if admin), and Sign Out button.
2. **Main Dialogue Column** (max width: 768px centered):
   - Messages scroll smoothly with auto-stick to bottom while streaming.
   - Pinned input container at bottom.

### Empty State (New Conversation)

- Clean welcome header: *"BRAC University AI Assistant"*.
- Subtitle: *"Ask any question regarding admissions, academic regulations, tuition fees, course advising, or campus facilities."*
- 4 clickable suggested prompt chips:
  1. *"What is the undergraduate tuition fee per credit?"*
  2. *"How does course probation and CGPA calculation work?"*
  3. *"What are the waiver criteria for meritorious students?"*
  4. *"Where is the registrar office located in the new campus?"*

### Message Rendering

- **User Messages**:
  - Right-aligned bubble using `--color-surface` with subtle border.
  - Plain text with preserved line breaks.
- **Assistant Messages**:
  - Left-aligned, no bubble, clean markdown rendering (`react-markdown` with `remark-gfm`).
  - Tables rendered with compact striped borders.
  - Lists and code blocks formatted cleanly.
  - While streaming: subtle blinking vertical bar caret at stream tail.
  - While waiting for initial tokens: three-dot pulse indicator with text: *"Searching university records..."*.
  - Message action toolbar (appears on hover or tap):
    - **Copy**: copies full markdown content to clipboard.
    - **Feedback**: Thumbs-up (+1) and Thumbs-down (-1) icons. Clicking opens an optional feedback dialog to submit details via `POST /api/v1/chat/messages/{id}/feedback`.
    - **Regenerate**: available on the last assistant response.

### Citations & Source Drawer

- Displayed immediately beneath assistant answers that utilized retrieved documents.
- Rendered as compact chips: `[Doc Title, Page X]` with a book/file icon.
- Clicking any citation chip opens a slide-over panel or popover showing:
  - Document Title and original source filename.
  - Page number and section heading (if available).
  - Exact quoted text snippet from the university record.
  - Retrieval relevance score badge.

### Out of Scope & Fallback Messages

- When queries cannot be answered from the knowledge base (retrieval score below threshold), the assistant responds:
  *"I could not find official information regarding this inquiry in the BRAC University knowledge base. Please contact the Admissions Office or Registrar directly for verified records."*
- Rendered in a muted tone with no source chips and institutional contact suggestions.

### Input Bar

- Centered, anchored at the bottom of the viewport.
- Auto-expanding textarea (1 to 6 lines) with `Enter` to send, `Shift+Enter` for multiline.
- Right-aligned Action Button:
  - Blue Send icon when idle with text.
  - Red Stop Square icon while streaming (aborts request via `AbortController`).
- Disclaimer caption below input: *"Responses are generated strictly from official BRAC University documents."*

---

## 5. SSE Streaming Protocol for Frontend

The chat client consumes `POST /api/v1/chat/stream` via `fetch` and `ReadableStream`:

```typescript
interface StreamEventPayload {
  event: "query_rewrite" | "sources" | "token" | "done" | "error";
  data: Record<string, unknown>;
}
```

1. **`query_rewrite`**:
   - Payload: `{ rewritten_query: string }`
   - UI Behavior: Displays a discrete status badge above the message: *"Searching for: [rewritten_query]"*.
2. **`sources`**:
   - Payload: `{ citations: CitationItem[] }`
   - UI Behavior: Populates the source citation chips under the active message.
3. **`token`**:
   - Payload: `{ token: string }`
   - UI Behavior: Appends tokens to the active assistant message state and scrolls to bottom.
4. **`done`**:
   - Payload: `{ session_id: string, message_id: string, full_text: string, fallback: boolean }`
   - UI Behavior: Finalizes the message state, assigns database `message_id`, enables feedback buttons, and updates conversation URL if session was just created.

---

## 6. Admin Knowledge Base (`/admin/knowledge`)

A purpose-built interface for university administrators to curate documents.

### Key Sections

1. **Top Actions Bar**:
   - **Upload File Button**: Drag-and-drop modal accepting PDF, DOCX, MD, and TXT files (up to 50MB).
   - **Add Web URL Button**: Input dialog accepting target BRACU webpage URL with recursive crawl depth option (0 to 2).
   - **Search & Filter Bar**: Filter documents by keyword, file type, or ingestion status.
2. **Documents Table** (shadcn/ui `Table`):
   - **Columns**: Title, Source Type (badge: PDF, DOCX, MD, URL), Chunks Count, Ingestion Status, Updated At, Actions.
   - **Status Badges**:
     - `completed`: Green badge.
     - `processing` / `pending`: Blue pulsing badge with progress indicator.
     - `failed`: Red badge with tooltip displaying parser or embedding error details.
   - **Row Actions**:
     - *Re-index*: Triggers document re-chunking and embedding (`POST /api/v1/documents/{id}/reindex`).
     - *Inspect Chunks*: Dialog previewing the document's stored chunks and token lengths.
     - *Delete*: Confirmation dialog deleting document and associated vector chunks (`DELETE /api/v1/documents/{id}`).
3. **Background Job Polling**:
   - While any document is `pending` or `processing`, the table polls `GET /api/v1/documents` every 4 seconds until tasks conclude.

---

## 7. Admin User Management (`/admin/users`)

Dedicated view for managing accounts and permissions.

- **User Table**:
  - Full Name, Email, Role (`admin` or `user`), Joined Date, Actions.
- **Role Elevation**:
  - Dropdown or toggle to change user role between `user` and `admin` (`PATCH /api/v1/users/{id}/role`).
  - Protected: admins cannot revoke their own admin permissions to prevent lockout.

---

## 8. Frontend Component Hierarchy

```
frontend/
  app/
    layout.tsx               (Root layout with fonts, theme provider, toast container)
    page.tsx                 (Root route redirect logic)
    (auth)/
      login/page.tsx         (Unified login page)
      register/page.tsx      (Student registration page)
    chat/
      page.tsx               (Fresh chat workspace)
      [id]/page.tsx          (Historical chat workspace)
    admin/
      layout.tsx             (Admin shell with sidebar navigation)
      knowledge/page.tsx     (Knowledge base table and upload controls)
      users/page.tsx         (User management table)
  components/
    chat/
      ChatContainer.tsx      (Main conversation controller and SSE stream handler)
      ChatMessageList.tsx    (Virtual or scrollable message list)
      ChatMessageItem.tsx    (Individual message bubble and markdown renderer)
      ChatInput.tsx          (Auto-resizing input box with stop/send controls)
      CitationChips.tsx      (Collapsible source chips and drawer viewer)
      FeedbackDialog.tsx     (Thumbs up/down feedback rating and comment modal)
      PromptSuggestions.tsx  (Starter prompt cards for new sessions)
    sidebar/
      AppSidebar.tsx         (Desktop sidebar and mobile drawer wrapper)
      SessionList.tsx        (Grouped list of chat sessions)
      SessionListItem.tsx    (Session title with rename/clear/delete actions)
      UserMenu.tsx           (Profile, theme toggle, admin link, logout)
    admin/
      DocumentsTable.tsx     (Knowledge base table with status indicators)
      UploadModal.tsx        (File drag and drop upload dropzone)
      UrlCrawlModal.tsx      (URL ingestion modal with crawl depth)
      UserTable.tsx          (Admin user management table)
    ui/                      (shadcn/ui primitives: button, input, dialog, table, etc.)
  lib/
    api/                     (Fetch wrapper with cookie credential handling)
    hooks/                   (useChatStream, useSessions, useTheme, useAuth)
    types/                   (TypeScript interfaces matching FastAPI OpenAPI schema)
  proxy.ts                   (Next.js 16 route protection and redirect proxy)
```

---

## 9. Error Handling & Edge States

1. **Network Loss during Streaming**: Inline notification banner with a "Retry" button. No intrusive alert modals.
2. **Expired Authentication**: Seamless refresh attempt via `POST /api/v1/auth/refresh`. If refresh token is expired, redirect to `/login` preserving current URL in `returnUrl`.
3. **Empty Knowledge Base**: If the knowledge base contains 0 documents, the admin dashboard displays a prominent onboarding prompt to ingest initial university documents.
4. **Token Limits**: Input box limits prompt length to 4000 characters with a live character count warning above 3800 characters.
