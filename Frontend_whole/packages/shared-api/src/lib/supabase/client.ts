/**
 * Single Supabase client for the whole app.
 *
 * Re-exports the generated singleton in `integrations/supabase/client.ts`
 * so there is exactly ONE `GoTrueClient` instance (multiple instances cause
 * auth state races and console warnings). Import from here in app code.
 */
export { supabase } from "../../integrations/supabase/client";
export type { Database } from "../../integrations/supabase/types";
