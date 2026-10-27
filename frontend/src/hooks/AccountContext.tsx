import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

type Account = { session: Session | null; loading: boolean; signOut: () => Promise<void> };
const AccountContext = createContext<Account>({
  session: null,
  loading: true,
  signOut: async () => {},
});

export function AccountProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(supabase));
  useEffect(() => {
    if (!supabase) return;
    let active = true;
    let revision = 0;
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      if (event === 'INITIAL_SESSION') return;
      revision++;
      if (active) {
        setSession(next && next.user.email_confirmed_at && !next.user.is_anonymous ? next : null);
        setLoading(false);
      }
    });
    const initialRevision = revision;
    void (async () => {
      try {
        const {
          data: { session: cached },
        } = await supabase!.auth.getSession();
        if (!cached) {
          if (active && revision === initialRevision) setSession(null);
          return;
        }
        // Verify persisted sessions with the Auth server before showing the workspace.
        const {
          data: { user },
          error,
        } = await supabase!.auth.getUser();
        if (active && revision === initialRevision)
          setSession(
            !error && user && user.email_confirmed_at && !user.is_anonymous
              ? { ...cached, user }
              : null,
          );
      } catch {
        if (active && revision === initialRevision) setSession(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);
  async function signOut() {
    setSession(null);
    if (supabase) await supabase.auth.signOut({ scope: 'local' });
  }
  return (
    <AccountContext.Provider value={{ session, loading, signOut }}>
      {children}
    </AccountContext.Provider>
  );
}
export const useAccount = () => useContext(AccountContext);
