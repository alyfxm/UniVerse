/**
 * Supabase Browser Client initialization using `@supabase/ssr`.
 */

import { createBrowserClient } from "@supabase/ssr";

export function getSupabaseBrowserClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (
    !supabaseUrl ||
    supabaseUrl.startsWith("https://your-project-ref") ||
    !supabaseKey ||
    supabaseKey.startsWith("your-")
  ) {
    return null;
  }

  return createBrowserClient(supabaseUrl, supabaseKey);
}

