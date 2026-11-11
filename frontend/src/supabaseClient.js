import { createClient } from '@supabase/supabase-js';
import { frontendConfiguration } from './frontendConfiguration';
import { AccountSession } from './accountSession';

const config = frontendConfiguration(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY);
export const accountSession = config ? new AccountSession(createClient(config.url, config.key, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
}).auth) : null;
