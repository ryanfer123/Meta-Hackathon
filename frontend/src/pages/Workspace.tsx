import * as m from 'motion/react-m';
import { AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import {
  BookOpen,
  Cloud,
  FileCheck2,
  House,
  LogIn,
  LogOut,
  Menu,
  Play,
  Save,
  X,
} from 'lucide-react';
import { Brand } from '../components/Brand';
import { AuthDialog } from '../components/AuthDialog';
import { Dialog } from '../components/Dialog';
import { useAccount } from '../hooks/AccountContext';
import { cloudConfigured } from '../lib/supabase';
import type { AnalysisJob } from '../lib/workspace';
import { saveRun } from '../lib/workspace';
import { getHealth, loadSample } from '../api';
import { Learn } from '../Learn';
import { Results } from '../Results';
import { Overview } from './Overview';
import { CheckRecording, type TaughtProcedure } from './Check';
import { RunLibrary } from './RunLibrary';
import { scenarios, type Run, type Health } from '../types';

const navigation = [
  { name: 'Home', view: 'Overview', icon: House },
  { name: 'Teach', view: 'Learn', icon: BookOpen },
  { name: 'Check', view: 'Check', icon: Play },
  { name: 'Results', view: 'Supervise', icon: FileCheck2 },
];
const aliases: Record<string, string> = {
  Home: 'Overview',
  Teach: 'Learn',
  Check: 'Check',
  Results: 'Supervise',
  'My runs': 'Run library',
  Overview: 'Overview',
  Learn: 'Learn',
  Supervise: 'Supervise',
  Audit: 'Audit',
  'Run library': 'Run library',
};
function initialView() {
  const params = new URLSearchParams(location.hash.split('?')[1]);
  const view = params.get('view') ?? 'Home';
  return view === 'Results' && params.get('tab') === 'Integrity'
    ? 'Audit'
    : (aliases[view] ?? 'Overview');
}
function routeParams(view: string, sample: string) {
  const next =
    view === 'Overview'
      ? 'Home'
      : view === 'Learn'
        ? 'Teach'
        : view === 'Run library'
          ? 'My runs'
          : ['Supervise', 'Audit'].includes(view)
            ? 'Results'
            : view;
  return new URLSearchParams({
    view: next,
    sample,
    ...(['Supervise', 'Audit'].includes(view)
      ? { tab: view === 'Audit' ? 'Integrity' : 'Replay' }
      : {}),
  });
}
export default function Workspace({ readOnly = false }: { readOnly?: boolean }) {
  const [view, setView] = useState(initialView),
    [scenario, setScenario] = useState(
      () => new URLSearchParams(location.hash.split('?')[1]).get('sample') || 'skipped-cap',
    );
  const [procedure, setProcedure] = useState<TaughtProcedure | null>(null);
  const [run, setRun] = useState<Run | null>(null),
    [health, setHealth] = useState<Health>({
      replay_mode: true,
      live_configured: false,
      glimmer_configured: false,
    });
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [auth, setAuth] = useState(false),
    [scope, setScope] = useState(false),
    [mobileMenu, setMobileMenu] = useState(false),
    [saving, setSaving] = useState(false),
    [toast, setToast] = useState(''),
    [refreshKey, setRefreshKey] = useState(0),
    [sampleRevision, setSampleRevision] = useState(0);
  const [source, setSource] = useState<{
      file: File;
      kind: 'expert' | 'held_out' | 'novice';
    } | null>(null),
    [learnJob, setLearnJob] = useState<AnalysisJob | null>(null);
  const { session, signOut } = useAccount();
  useEffect(() => {
    if (!readOnly) void getHealth().then(setHealth);
  }, [readOnly]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void loadSample(scenario)
      .then((r) => {
        if (active) setRun(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [scenario, sampleRevision]);
  useEffect(() => {
    const sync = () => {
      const params = new URLSearchParams(location.hash.split('?')[1]);
      setView(initialView());
      const name = params.get('sample');
      if (scenarios.some(([id]) => id === name)) {
        setLoading(true);
        setScenario(name!);
        setSampleRevision((value) => value + 1);
      }
      setMobileMenu(false);
    };
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(''), 5000);
    return () => clearTimeout(id);
  }, [toast]);
  function goView(requested: string) {
    const next = aliases[requested] ?? 'Overview';
    if (readOnly && next === 'Run library') {
      setAuth(true);
      setMobileMenu(false);
      return;
    }
    setView(next);
    setMobileMenu(false);
    const params = routeParams(next, scenario);
    history.replaceState(null, '', `#/workspace?${params}`);
  }
  function chooseScenario(name: string) {
    setLoading(true);
    setSampleRevision((value) => value + 1);
    setScenario(name);
    setView('Supervise');
    setMobileMenu(false);
    history.replaceState(null, '', `#/workspace?${routeParams('Supervise', name)}`);
  }
  async function persist() {
    if (!session) {
      setAuth(true);
      return;
    }
    if (!run) return;
    setSaving(true);
    setError('');
    try {
      await saveRun(run);
      setToast('Run saved to your private library.');
      setRefreshKey((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this run. Try again.');
    } finally {
      setSaving(false);
    }
  }
  const heading =
    view === 'Learn'
      ? 'Teach'
      : view === 'Run library'
        ? 'My runs'
        : view === 'Check'
          ? 'Check'
          : ['Supervise', 'Audit'].includes(view)
            ? 'Results'
            : 'Home';
  return (
    <div className="workspace-scope">
      <a className="skip-link" href="#workspace-main">
        Skip to main content
      </a>
      <aside className={`workspace-sidebar ${mobileMenu ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <a href="#" aria-label="Apprentice home">
            <Brand />
          </a>
          <button
            className="icon-button sidebar-close"
            onClick={() => setMobileMenu(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>
        <nav aria-label="Workspace">
          {navigation.map(({ name, view: target, icon: Icon }) => (
            <button
              key={name}
              className={
                view === target || (target === 'Supervise' && view === 'Audit') ? 'active' : ''
              }
              onClick={() => goView(target)}
              aria-current={
                view === target || (target === 'Supervise' && view === 'Audit') ? 'page' : undefined
              }
            >
              <Icon size={20} />
              {name}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button onClick={() => setScope(true)}>About these examples</button>
          <div className="sidebar-account">
            <p>
              {session
                ? 'Your recordings and saved results belong to your account.'
                : 'Try the examples. Sign in to use your own recordings.'}
            </p>
          </div>
          <button className="account-action" onClick={() => goView('Run library')}>
            My runs
          </button>
          {session ? (
            <button className="account-action" onClick={() => void signOut()}>
              <LogOut size={17} />
              Sign out
            </button>
          ) : (
            <button className="account-action" onClick={() => setAuth(true)}>
              <LogIn size={17} />
              Sign in
            </button>
          )}
        </div>
      </aside>
      {mobileMenu && (
        <button
          className="mobile-scrim"
          onClick={() => setMobileMenu(false)}
          aria-label="Dismiss navigation"
        />
      )}
      <div className="workspace-body">
        <header className="workspace-topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileMenu(true)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <span>
              Workspace <span className="breadcrumb-divider">/</span> <strong>{heading}</strong>
            </span>
          </div>
          <div>
            <span className="cloud-status">
              <Cloud size={18} />
              {session ? 'Private workspace' : 'Sample workspace'}
            </span>
            {!!session &&
              run?.provenance === 'live-recording' &&
              ['Supervise', 'Audit'].includes(view) && (
                <button
                  className="button primary save-run"
                  onClick={() => void persist()}
                  disabled={!run || saving}
                >
                  <Save size={16} />
                  {saving ? 'Saving…' : 'Save run'}
                </button>
              )}
          </div>
        </header>
        {readOnly && !['Supervise', 'Audit'].includes(view) && (
          <div className="sample-access-banner" role="note">
            <span>Example mode — sign in to check your own recordings.</span>
            <button className="text-button" onClick={() => setAuth(true)}>
              Sign in
            </button>
          </div>
        )}
        <main id="workspace-main" className="workspace-main">
          <div className="workspace-title">
            <div>
              <h1>{heading}</h1>
              <p>
                {view === 'Supervise'
                  ? 'Play the recording, follow each step, and select an alert to see what happened.'
                  : view === 'Learn'
                    ? 'Turn an example video into a checklist. Review the steps before using it.'
                    : view === 'Audit'
                      ? 'Review flagged steps, download the report, and check that its event log is unchanged.'
                      : view === 'Run library'
                        ? 'Keep the source recordings and the useful results.'
                        : view === 'Check'
                          ? 'Compare a new recording with the steps you taught.'
                          : 'Watch an example, then try your own recording.'}
              </p>
            </div>
          </div>
          {['Supervise', 'Audit'].includes(view) && (
            <>
              {view === 'Supervise' && run?.provenance === 'synthetic' && (
                <div className="sample-chips" aria-label="Animated examples">
                  {scenarios.map(([id, title]) => (
                    <button
                      className="button"
                      key={id}
                      aria-pressed={scenario === id}
                      onClick={() => chooseScenario(id)}
                    >
                      {scenario === id && <span aria-hidden="true">✓ </span>}
                      {title}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
          {error && (
            <p className="error-message" role="alert">
              {error}
              <button className="text-button" onClick={() => setError('')}>
                Dismiss
              </button>
            </p>
          )}
          <m.div
            key={view}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28 }}
          >
            {view === 'Overview' ? (
              <Overview
                onView={goView}
                onScenario={chooseScenario}
                onSignIn={() => setAuth(true)}
                signedIn={!!session}
              />
            ) : view === 'Check' ? (
              <CheckRecording
                procedure={procedure}
                health={health}
                readOnly={readOnly}
                source={source?.kind === 'novice' ? source.file : null}
                onTeach={() => goView('Learn')}
                onSample={() => chooseScenario('skipped-cap')}
                onSignIn={() => setAuth(true)}
                onRun={(result) => {
                  setRun(result);
                  goView('Supervise');
                }}
              />
            ) : view === 'Run library' ? (
              <RunLibrary
                userId={session?.user.id}
                onSignIn={() => setAuth(true)}
                onOpen={(r) => {
                  setRun(r);
                  goView('Supervise');
                }}
                refreshKey={refreshKey}
                onUse={(file, kind) => {
                  if (kind === 'expert') {
                    setLearnJob(null);
                    setProcedure(null);
                  }
                  setSource({ file, kind });
                  goView(kind === 'novice' ? 'Check' : 'Learn');
                }}
                onResume={(job) => {
                  if (job.kind === 'run') {
                    setRun(job.result as unknown as Run);
                    goView('Supervise');
                  } else {
                    setSource(null);
                    setLearnJob(job);
                    goView('Learn');
                  }
                }}
              />
            ) : loading || !run ? (
              <div className="loading" role="status">
                <span className="spinner" />
                Loading the procedure…
              </div>
            ) : (
              <>
                {['Supervise', 'Audit'].includes(view) && (
                  <Results
                    key={run.id}
                    run={run}
                    initialTab={view === 'Audit' ? 'Integrity' : 'Replay'}
                    onTabChange={(tab) => goView(tab === 'Integrity' ? 'Audit' : 'Supervise')}
                    readOnly={readOnly}
                    onSignIn={() => setAuth(true)}
                  />
                )}
              </>
            )}
          </m.div>
          {run && !loading && (
            <m.div
              hidden={view !== 'Learn'}
              animate={{ opacity: view === 'Learn' ? 1 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <Learn
                onProtocolReady={setProcedure}
                onNavigateCheck={() => goView('Check')}
                readOnly={readOnly}
                onSignIn={() => setAuth(true)}
                run={run}
                health={health}
                source={source}
                initialJob={learnJob}
                onRun={(r) => {
                  setRun(r);
                  goView('Supervise');
                }}
              />
            </m.div>
          )}
        </main>
        <footer className="workspace-footer">
          <span>
            {run?.provenance === 'live-recording' ? 'Recorded evidence' : 'Animated example'} ·{' '}
            {session
              ? cloudConfigured
                ? 'Private storage connected'
                : 'Local preview'
              : 'No account needed for examples'}
          </span>
          <a
            href="https://github.com/ryanfer123/Meta-Hackathon"
            target="_blank"
            rel="noopener noreferrer"
          >
            View source
          </a>
        </footer>
      </div>
      <AnimatePresence>
        {toast && (
          <m.div
            key="notification"
            className="toast"
            role="status"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2 }}
          >
            {toast}
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() => setToast('')}
            >
              <X size={17} />
            </button>
          </m.div>
        )}
      </AnimatePresence>
      {auth && <AuthDialog onClose={() => setAuth(false)} />}{' '}
      {scope && (
        <Dialog title="About these examples" onClose={() => setScope(false)}>
          <div className="provenance-copy">
            <p>
              The examples are animated, not camera recordings. They show how the app works; no
              models ran for them.
            </p>
            <p>
              Your recordings and saved results are private to your account. Signing in does not
              turn an animated example into a real recording.
            </p>
            <p>
              Geometry can observe handling. It cannot prove concentration, transferred volume,
              sterility, or a tightly secured cap. Unseen actions remain uncertain.
            </p>
            <p>
              Accuracy on real procedure videos is still being evaluated. Diagnostic model calls are
              not a procedure evaluation.
            </p>
          </div>
          <button className="button primary" onClick={() => setScope(false)}>
            Back to the app
          </button>
        </Dialog>
      )}
    </div>
  );
}
