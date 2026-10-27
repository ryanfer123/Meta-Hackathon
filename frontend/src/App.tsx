import { lazy, Suspense, useEffect, useState } from 'react';
import { HomePage } from './pages/HomePage';
const Workspace = lazy(() => import('./pages/Workspace'));

export function App() {
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
