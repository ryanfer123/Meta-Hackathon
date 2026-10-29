import * as m from 'motion/react-m';
import { useReducedMotion } from 'motion/react';
import { useEffect, useState } from 'react';
import { ArrowRight, Check, Play, AlertCircle, ExternalLink } from 'lucide-react';
import { Brand } from '../components/Brand';
import { Scene } from '../Scene';
import { loadSample } from '../api';
import type { Run } from '../types';

interface Props {
  onOpen: (scenario?: string, view?: string) => void;
}
const stages = [
  {
    title: 'Teach',
    copy: 'Upload an example video with narration. Review the suggested checklist and test it with a second example.',
    image: 'learn',
    alt: 'Sample checklist with four checks still waiting for real example videos',
  },
  {
    title: 'Check',
    copy: 'Compare another recording with the checklist. See which steps were observed, missed, or done in the wrong order.',
    image: 'supervise',
    alt: 'Animated sample showing a missed cap step beside the playback',
  },
  {
    title: 'Results',
    copy: 'Review the flagged moments and download a report. Sign in to save recordings and results in your private library.',
    image: 'audit',
    alt: 'Sample report showing observed steps, flagged events, and unmeasured model results',
  },
];

export function HomePage({ onOpen }: Props) {
  const reducedMotion = useReducedMotion();
  const reveal = {
    initial: reducedMotion ? (false as const) : { opacity: 0, y: 24 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.15 },
  };
  const [comparison, setComparison] = useState<'clean' | 'skipped-cap'>('skipped-cap');
  const [samples, setSamples] = useState<Record<string, Run>>({});
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void Promise.all(['clean', 'skipped-cap'].map(loadSample))
      .then(([clean, skipped]) => {
        if (active) setSamples({ clean, 'skipped-cap': skipped });
      })
      .catch(() => {
        if (active) setError('The replay could not load. Try the example to try again.');
      });
    return () => {
      active = false;
    };
  }, []);
  const run = samples[comparison];
  const final = run?.frames.find((f) => f.t === 17) ?? run?.frames.at(-1);
  return (
    <div className="home-page">
      <a className="skip-link" href="#home-main">
        Skip to main content
      </a>
      <header className="home-nav">
        <a href="#" aria-label="Apprentice home">
          <Brand />
        </a>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#evidence">The evidence</a>
          <a
            href="https://github.com/ryanfer123/Meta-Hackathon"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <button onClick={() => onOpen()}>
            Open Apprentice <ArrowRight size={17} />
          </button>
        </nav>
      </header>
      <main id="home-main">
        <section className="home-hero">
          <m.div
            className="hero-copy"
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
          >
            <m.h1
              variants={{
                hidden: { opacity: 0, y: reducedMotion ? 0 : 22 },
                visible: { opacity: 1, y: 0 },
              }}
            >
              Show it once.
              <br />
              Check each step.
            </m.h1>
            <m.p
              variants={{
                hidden: { opacity: 0, y: reducedMotion ? 0 : 22 },
                visible: { opacity: 1, y: 0 },
              }}
            >
              Apprentice turns an example video into a step-by-step checklist, then checks another
              recording for missed steps and actions in the wrong order.
            </m.p>
            <m.button
              variants={{
                hidden: { opacity: 0, y: reducedMotion ? 0 : 22 },
                visible: { opacity: 1, y: 0 },
              }}
              className="home-button"
              onClick={() => onOpen('skipped-cap', 'Supervise')}
            >
              <span className="play-disc">
                <Play size={18} fill="currentColor" />
              </span>
              See it catch a mistake (30 seconds)
            </m.button>
          </m.div>
          <m.div
            className="hero-orbit"
            initial={reducedMotion ? false : { opacity: 0, x: 48, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
          >
            <img
              src={`${import.meta.env.BASE_URL}images/procedure-studio.webp`}
              width="1500"
              height="1500"
              alt="Illustrative studio arrangement of colored-water tubes and a dropper"
              fetchPriority="high"
            />
          </m.div>
          <p className="hero-caption">
            Illustration, not camera footage. Try the animated sample without signing in.
          </p>
        </section>
        <section className="home-comparison" id="evidence">
          <div className="home-section-heading">
            <m.h2 {...reveal} className="reveal">
              See the difference.
            </m.h2>
            <m.p {...reveal} className="reveal">
              Compare two animated examples: one follows every step; the other misses a cap. Open
              either example to see what happened and when.
            </m.p>
          </div>
          <m.div {...reveal} className="comparison-product reveal" data-ui>
            <div className="comparison-toolbar">
              <span>Colored-water handling</span>
              <div className="segmented" aria-label="Compare procedure runs">
                <button
                  aria-pressed={comparison === 'clean'}
                  onClick={() => setComparison('clean')}
                >
                  Clean run
                </button>
                <button
                  aria-pressed={comparison === 'skipped-cap'}
                  onClick={() => setComparison('skipped-cap')}
                >
                  Skipped cap
                </button>
              </div>
            </div>
            <m.div
              className="comparison-layout"
              key={comparison}
              initial={{ opacity: reducedMotion ? 1 : 0.5 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25 }}
            >
              <div className="comparison-scene">
                {final ? (
                  <Scene frame={final} masks />
                ) : (
                  <div className="comparison-loading">{error || 'Loading the replay…'}</div>
                )}
                <div className="comparison-clock">
                  <Play size={14} fill="currentColor" />
                  <span>00:17</span>
                  <div className="comparison-track">
                    <span />
                  </div>
                  <span>00:24</span>
                </div>
              </div>
              <div className="comparison-steps">
                <h3>Step checklist</h3>
                {run?.protocol.steps.map((s) => {
                  const missed = comparison === 'skipped-cap' && s.id === 'cap';
                  return (
                    <div
                      className={missed ? 'comparison-step missed' : 'comparison-step'}
                      key={s.id}
                    >
                      {missed ? <AlertCircle size={22} /> : <Check size={22} />}
                      <span>{s.title}</span>
                      <small>{missed ? 'Skipped' : 'Observed'}</small>
                    </div>
                  );
                })}
                <p>An animated example checked by the same rules used in the app.</p>
              </div>
            </m.div>
            <div className="comparison-bottom">
              <div
                className={
                  comparison === 'skipped-cap'
                    ? 'comparison-observation deviation'
                    : 'comparison-observation'
                }
              >
                <span>00:17</span>
                <strong>
                  {comparison === 'skipped-cap'
                    ? 'The cap step was missed.'
                    : 'All steps were observed in order.'}
                </strong>
              </div>
              <button className="button primary" onClick={() => onOpen(comparison, 'Supervise')}>
                Open this sample <ArrowRight size={17} />
              </button>
            </div>
          </m.div>
          <p className="home-note">
            Animated sample, not a real recording. Accuracy on real videos has not been measured.
          </p>
        </section>
        <section className="home-method" id="how-it-works">
          <m.h2 {...reveal} className="reveal">
            From example to review.
          </m.h2>
          <div className="method-stages">
            {stages.map((stage) => (
              <article key={stage.title}>
                <m.h3 {...reveal} className="reveal">
                  {stage.title}
                </m.h3>
                <m.p {...reveal} className="reveal">
                  {stage.copy}
                </m.p>
                <m.button
                  {...reveal}
                  className="method-image reveal"
                  whileHover={{ y: -4 }}
                  whileTap={{ scale: 0.985 }}
                  onClick={() =>
                    onOpen(
                      'skipped-cap',
                      stage.image === 'learn'
                        ? 'Learn'
                        : stage.image === 'audit'
                          ? 'Audit'
                          : 'Supervise',
                    )
                  }
                  aria-label={
                    stage.image === 'learn'
                      ? 'Open Teach'
                      : stage.image === 'supervise'
                        ? 'See an example check'
                        : 'View the sample report'
                  }
                >
                  <img
                    src={`${import.meta.env.BASE_URL}images/product-${stage.image}.png`}
                    width="960"
                    height="600"
                    alt={stage.alt}
                    loading="lazy"
                  />
                  <span>
                    {stage.image === 'learn'
                      ? 'Open Teach'
                      : stage.image === 'supervise'
                        ? 'See an example check'
                        : 'View the sample report'}{' '}
                    <ArrowRight size={17} />
                  </span>
                </m.button>
              </article>
            ))}
          </div>
        </section>
        <section className="home-evidence">
          <div className="evidence-copy">
            <m.h2 {...reveal} className="reveal">
              See why a step was flagged.
            </m.h2>
            <m.p {...reveal} className="reveal">
              Select an alert to jump to that moment. See what the checklist expected and what was
              visible in the recording.
            </m.p>
            <m.button
              {...reveal}
              className="home-link reveal"
              onClick={() => onOpen('skipped-cap', 'Audit')}
            >
              View the sample report <ArrowRight size={21} />
            </m.button>
          </div>
          <m.div {...reveal} className="evidence-example reveal" data-ui>
            <span className="evidence-time">00:17</span>
            <h3>Cap tube 1</h3>
            <p className="evidence-status">
              <AlertCircle size={20} />
              Skipped
            </p>
            <p>The label was placed before the cap step was observed.</p>
            <div className="evidence-rule">
              <span>Expected observation</span>
              <strong>The blue cap touches tube 1.</strong>
            </div>
            <p className="evidence-disclosure">
              Seeing a cap touch a tube does not prove it is tight. If the view is blocked, the
              result stays uncertain.
            </p>
          </m.div>
        </section>
        <section className="home-close">
          <m.h2 {...reveal} className="reveal">
            Your next run starts here.
          </m.h2>
          <div className="home-close-row">
            <m.p {...reveal} className="reveal">
              Try an animated sample with no account. Sign in when you want to upload your own
              example and comparison recordings.
            </m.p>
            <m.button
              {...reveal}
              className="home-button reveal"
              onClick={() => onOpen('skipped-cap', 'Supervise')}
            >
              Try the example <ArrowRight size={21} />
            </m.button>
          </div>
          <m.p {...reveal} className="home-note reveal">
            The samples demonstrate how the app works. Checks on real recordings are still being
            evaluated; the app does not verify liquid volume, concentration, or cap tightness.
          </m.p>
        </section>
      </main>
      <footer className="home-footer">
        <div>
          <Brand />
          <a
            href="https://github.com/ryanfer123/Meta-Hackathon"
            target="_blank"
            rel="noopener noreferrer"
          >
            Built in the open <ExternalLink size={16} />
          </a>
        </div>
        <p>Suggested steps. Visible evidence. Clear reasons.</p>
        <span className="footer-word">apprentice</span>
      </footer>
    </div>
  );
}
