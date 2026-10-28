import { LazyMotion, MotionConfig } from 'motion/react';
import { lazy, Suspense, useEffect, useState } from 'react';
import { AccountProvider, useAccount } from './hooks/AccountContext';
import { AuthDialog } from './components/AuthDialog';
import { Brand } from './components/Brand';
import { HomePage } from './pages/HomePage';
const loadMotion = () => import('./motionFeatures').then((module) => module.default);
const Workspace = lazy(() => import('./pages/Workspace'));

export function App() {
  return (
    <LazyMotion features={loadMotion} strict>
      <MotionConfig reducedMotion="user" transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
        <AccountProvider>
          <Routes />
        </AccountProvider>
      </MotionConfig>
    </LazyMotion>
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
  function open(scenario = 'skipped-cap', view = 'Supervise') {
    location.hash = `/workspace?${new URLSearchParams({ sample: scenario, view })}`;
  }
  const workspace = hash.startsWith('#/workspace') || hash.includes('access_token=');
  if (workspace && loading)
    return (
      <div className="app-loading" role="status">
        Checking your session…
      </div>
    );
  if (workspace && !session)
    return (
      <div className="auth-page">
        <header>
          <a href="#" aria-label="Apprentice home">
            <Brand />
          </a>
          <a href="#">Back to home</a>
        </header>
        <main>
          <div className="auth-story">
            <h2>
              Good work.
              <br />
              Kept together.
            </h2>
            <p>
              Sign in to review procedures, save evidence, and keep your recordings in your own
              workspace.
            </p>
            <img
              src={`${import.meta.env.BASE_URL}images/procedure-studio.webp`}
              alt="Illustrative colored-water procedure setup"
            />
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
      <Workspace />
    </Suspense>
  ) : (
    <HomePage onOpen={open} />
  );
}
