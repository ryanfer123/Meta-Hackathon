import { useState } from 'react';
import { Mail, LockKeyhole } from 'lucide-react';
import { Dialog } from './Dialog';
import { supabase } from '../lib/supabase';

export function AuthDialog({
  onClose,
  onAuthenticated,
  inline = false,
}: {
  onClose: () => void;
  onAuthenticated?: () => void;
  inline?: boolean;
}) {
  const success = onAuthenticated ?? onClose;
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState(''),
    [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [error, setError] = useState('');
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (mode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        success();
      } else {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${location.origin}/#/workspace` },
        });
        if (error) throw error;
        if (data.session) success();
        else setMessage('Check your email to confirm your account, then sign in here.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not sign in. Try again.');
    } finally {
      setBusy(false);
    }
  }
  const title = mode === 'signin' ? 'Your private workspace' : 'Create your workspace';
  const content = (
    <>
      <p className="dialog-description">
        Sign in to review procedures, save runs, and store recordings. An account is required to
        enter the workstation.
      </p>
      <form className="auth-form" onSubmit={(e) => void submit(e)}>
        <label htmlFor="account-email">Email</label>
        <div className="input-with-icon">
          <Mail size={18} />
          <input
            id="account-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="you@example.com"
          />
        </div>
        <label htmlFor="account-password">Password</label>
        <div className="input-with-icon">
          <LockKeyhole size={18} />
          <input
            id="account-password"
            type="password"
            minLength={8}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="At least 8 characters"
          />
        </div>
        <button className="button primary full" disabled={busy || !supabase}>
          {busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </button>
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p className="notice" role="status">
            {message}
          </p>
        )}
      </form>
      {!supabase && <p className="notice">Cloud storage is not configured on this installation.</p>}
      <button
        className="text-button auth-switch"
        onClick={() => {
          setMode(mode === 'signin' ? 'signup' : 'signin');
          setError('');
          setMessage('');
        }}
      >
        {mode === 'signin' ? 'New here? Create an account' : 'Already have an account? Sign in'}
      </button>
      <button className="text-button guest-link" onClick={onClose}>
        Back to the homepage
      </button>
    </>
  );
  return inline ? (
    <section className="auth-card">
      <h1>{title}</h1>
      {content}
    </section>
  ) : (
    <Dialog title={title} onClose={onClose}>
      {content}
    </Dialog>
  );
}
