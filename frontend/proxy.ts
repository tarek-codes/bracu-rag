import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic route protection. Reads the role claim from the access token cookie
 * without verifying the signature: this only drives redirects. The FastAPI backend
 * verifies every token and remains the real authority (401/403).
 */
function readRole(token: string | undefined): "admin" | "user" | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      role?: string;
      exp?: number;
    };
    if (json.exp && json.exp * 1000 < Date.now()) return null;
    return json.role === "admin" ? "admin" : "user";
  } catch {
    return null;
  }
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const role = readRole(request.cookies.get("access_token")?.value);
  const hasRefresh = request.cookies.has("refresh_token");
  const signedIn = role !== null || hasRefresh;
  const home = role === "admin" ? "/admin/knowledge" : "/chat";
  const redirect = (to: string) => NextResponse.redirect(new URL(to, request.url));

  if (pathname === "/") return redirect(role ? home : "/chat");

  // Signed in visitors do not need the auth pages.
  if ((pathname === "/login" || pathname === "/register") && role) return redirect(home);

  if (pathname.startsWith("/admin")) {
    if (!signedIn) return redirect(`/login?returnUrl=${encodeURIComponent(pathname + search)}`);
    // Expired access token with a refresh cookie: let the client refresh, the page re-checks the role.
    if (role === "user") return redirect("/chat");
  }

  // Saved conversations belong to an account. Guests may only use the fresh /chat page.
  if (pathname.startsWith("/chat/") && !signedIn) {
    return redirect(`/login?returnUrl=${encodeURIComponent(pathname)}`);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/login", "/register", "/chat/:path*", "/admin/:path*"],
};
