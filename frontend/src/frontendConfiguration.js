// Both fields are public. Never accept service_role, secret keys, or DB passwords.
export function frontendConfiguration(url = '', key = '') {
  if (!url && !key) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password ||
        (parsed.pathname !== '' && parsed.pathname !== '/') || parsed.search || parsed.hash ||
        !key.startsWith('sb_publishable_')) throw new Error();
    return { url: parsed.origin, key };
  } catch {
    // Build tools may print this message: it must never include either value.
    throw new Error('Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY using the project HTTPS URL and publishable key only.');
  }
}
