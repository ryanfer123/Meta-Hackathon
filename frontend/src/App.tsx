import { LazyMotion, MotionConfig } from 'motion/react';
import { lazy, Suspense, useEffect, useState } from 'react';
import { AccountProvider, useAccount } from './hooks/AccountContext';
import { AuthDialog } from './components/AuthDialog';
import { Brand } from './components/Brand';
import { scenarios } from './types';
import { HomePage } from './pages/HomePage';
import { ThemeProvider } from './hooks/ThemeContext';
import { ThemeToggle } from './components/ThemeToggle';
import { motionTokens } from './lib/motion-tokens';
const loadMotion = () => import('./motionFeatures').then((module) => module.default);
const Workspace = lazy(() => import('./pages/Workspace'));

export function App() {
  return (
    <ThemeProvider>
      <LazyMotion features={loadMotion} strict>
        <MotionConfig
          reducedMotion="user"
          transition={{ duration: motionTokens.duration.normal, ease: motionTokens.easing.smooth }}
        >
          <AccountProvider>
            <Routes />
          </AccountProvider>
        </MotionConfig>
      </LazyMotion>
    </ThemeProvider>
  );
}
function Routes() {
  const { session, loading } = useAccount();
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const update = () => {
      setHash(location.hash);
      if (location.hash.startsWith('#/workspace')) scrollTo(0, 0);
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  function open(scenario?: string, view = 'Home') {
    const aliases: Record<string, string> = {
      Learn: 'Teach',
      Supervise: 'Results',
      Audit: 'Results',
      Overview: 'Home',
      'Run library': 'My runs',
    };
    const tab =
      view === 'Audit'
        ? 'Integrity'
        : view === 'Supervise' || view === 'Results'
          ? 'Replay'
          : undefined;
    location.hash = `/workspace?${new URLSearchParams({ ...(scenario ? { sample: scenario } : {}), view: aliases[view] ?? view, ...(tab ? { tab } : {}) })}`;
  }
  const workspace = hash.startsWith('#/workspace') || hash.includes('access_token=');
  const params = new URLSearchParams(hash.split('?')[1]);
  const publicSample =
    hash.startsWith('#/workspace?') &&
    scenarios.some(([name]) => name === params.get('sample')) &&
    ['Supervise', 'Audit', 'Learn', 'Teach', 'Results', 'Home', 'Overview', 'Check'].includes(
      params.get('view') ?? '',
    );
  if (workspace && !publicSample && loading)
    return (
      <div className="app-loading" role="status">
        Checking your session…
      </div>
    );
  if (workspace && !publicSample && !session)
    return (
      <div className="auth-page">
        <header>
          <a href="#" aria-label="Apprentice home">
            <Brand />
          </a>
          <div className="auth-header-actions">
            <ThemeToggle compact />
            <a href="#">Back to home</a>
          </div>
        </header>
        <main>
          <div className="auth-story">
            <h2>
              Your recordings.
              <br />
              Kept private.
            </h2>
            <p>Sign in to teach a procedure, check a recording, and save your results.</p>
            <p className="auth-workflow">
              Teach a procedure → Check another take → Review the evidence
            </p>
          </div>
          <AuthDialog
            inline
            onClose={() => {
              location.hash = '';
            }}
            onAuthenticated={() => {}}
          />
        </main>
      </div>
    );
  return workspace ? (
    <Suspense
      fallback={
        <div className="app-loading">
          <span className="spinner" />
          Opening the workstation…
        </div>
      }
    >
      <Workspace key={session?.user.id ?? 'public-sample'} readOnly={!session} />
    </Suspense>
  ) : (
    <HomePage onOpen={open} />
  );
}
