"use client";

import { createBrowserClient } from "@supabase/ssr";

export const supabaseConfigured =
  !!process.env.NEXT_PUBLIC_SUPABASE_URL &&
  !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// A browser Supabase client. When Supabase env vars are absent (local dev with
// the API running in QA_AGENT_AUTH_DISABLED mode) callers fall back to no auth.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
