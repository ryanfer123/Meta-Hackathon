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
    title: 'Learn',
    copy: 'Start with an expert demonstration. Inspect the proposed steps and the checks that make them meaningful.',
    image: 'learn',
    alt: 'The Apprentice protocol compiler and its validation checks',
  },
  {
    title: 'Observe',
    copy: 'Follow the next run, step by step. Open an observation to see why the procedure diverged.',
    image: 'supervise',
    alt: 'The Apprentice supervision workspace with a skipped-cap observation',
  },
  {
    title: 'Keep the evidence',
    copy: 'Save the run to your private library. Export an audit and keep its verification root separately.',
    image: 'audit',
    alt: 'The Apprentice audit with its evidence chain and verification controls',
  },
];

export function HomePage({ onOpen }: Props) {
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
        if (active) setError('The replay could not load. Open the workstation to try again.');
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    document.querySelectorAll('.reveal').forEach((el) => {
      el.classList.add('will-reveal');
      observer.observe(el);
    });
    return () => observer.disconnect();
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
            Open workspace <ArrowRight size={17} />
          </button>
        </nav>
      </header>
      <main id="home-main">
        <section className="home-hero">
          <div className="hero-copy">
            <h1>
              Good work.
              <br />
              Worth repeating.
            </h1>
            <p>
              Turn a demonstration into a procedure you can inspect. Catch the moment a later run
              goes off course.
            </p>
            <button className="home-button" onClick={() => onOpen()}>
              <span className="play-disc">
                <Play size={18} fill="currentColor" />
              </span>
              Try the workstation
            </button>
          </div>
          <div className="hero-orbit">
            <img
              src={`${import.meta.env.BASE_URL}images/procedure-studio.webp`}
              width="1500"
              height="1500"
              alt="Illustrative studio arrangement of colored-water tubes and a dropper"
              fetchPriority="high"
            />
          </div>
          <p className="hero-caption">
            Illustrative setup. The interactive demo uses synthetic masks.
          </p>
        </section>
        <section className="home-comparison" id="evidence">
          <div className="home-section-heading">
            <h2 className="reveal">See the difference.</h2>
            <p className="reveal">
              The same protocol. A clean run, or a missing cap. Every decision leads back to an
              observation.
            </p>
          </div>
          <div className="comparison-product reveal" data-ui>
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
            <div className="comparison-layout">
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
                <h3>What was observed</h3>
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
                <p>These results come from the rule engine's synthetic fixtures.</p>
              </div>
            </div>
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
                    ? 'Cap tube 1 was not observed.'
                    : 'Every step was observed in order.'}
                </strong>
              </div>
              <button className="button primary" onClick={() => onOpen(comparison)}>
                Inspect this run <ArrowRight size={17} />
              </button>
            </div>
          </div>
          <p className="home-note">Synthetic replay. No model accuracy is claimed.</p>
        </section>
        <section className="home-method" id="how-it-works">
          <h2 className="reveal">A procedure, with a memory.</h2>
          <div className="method-stages">
            {stages.map((stage) => (
              <article key={stage.title}>
                <h3 className="reveal">{stage.title}</h3>
                <p className="reveal">{stage.copy}</p>
                <button
                  className="method-image reveal"
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
                  aria-label={`Open ${stage.title.toLowerCase()} workspace`}
                >
                  <img
                    src={`${import.meta.env.BASE_URL}images/product-${stage.image}.webp`}
                    width="960"
                    height="600"
                    alt={stage.alt}
                    loading="lazy"
                  />
                  <span>
                    Open {stage.title.toLowerCase()} <ArrowRight size={17} />
                  </span>
                </button>
              </article>
            ))}
          </div>
        </section>
        <section className="home-evidence">
          <div className="evidence-copy">
            <h2 className="reveal">Follow the evidence.</h2>
            <p className="reveal">
              A red alert should come with a reason. Open the event, inspect the rule, and follow
              the observation back to its frame.
            </p>
            <button className="home-link reveal" onClick={() => onOpen('skipped-cap', 'Audit')}>
              Explore an audit <ArrowRight size={21} />
            </button>
          </div>
          <div className="evidence-example reveal" data-ui>
            <span className="evidence-time">00:17</span>
            <h3>Cap tube 1</h3>
            <p className="evidence-status">
              <AlertCircle size={20} />
              Skipped
            </p>
            <p>The label action was observed before the cap step.</p>
            <div className="evidence-rule">
              <span>Expected observation</span>
              <strong>The blue cap touches tube 1.</strong>
            </div>
            <p className="evidence-disclosure">
              A visible contact is not proof of a tightly secured cap. Missing pixels stay
              uncertain.
            </p>
          </div>
        </section>
        <section className="home-close">
          <h2 className="reveal">Your next run starts here.</h2>
          <div className="home-close-row">
            <p className="reveal">
              Explore the replay now. Bring your own recordings when you are ready to put the
              protocol to work.
            </p>
            <button className="home-button reveal" onClick={() => onOpen()}>
              Open the workstation <ArrowRight size={21} />
            </button>
          </div>
          <p className="home-note reveal">
            Meta inference and real-video evaluation are still being validated. The hosted examples
            are synthetic.
          </p>
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
        <p>Models propose. Pixels ground. Code decides.</p>
        <span className="footer-word">apprentice</span>
      </footer>
    </div>
  );
}
