import { redirect } from "next/navigation";

// proxy.ts routes "/" by role; this is a fallback.
export default function Home() {
  redirect("/chat");
}
