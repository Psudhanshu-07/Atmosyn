import { createClient as createSupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

export const createClient = () =>
  createSupabaseClient(supabaseUrl!, supabaseKey!, {
    auth: {
      persistSession: true,
      storage:
        typeof window !== "undefined" ? window.localStorage : undefined,
    },
  });