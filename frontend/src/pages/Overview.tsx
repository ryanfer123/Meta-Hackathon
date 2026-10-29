import { ArrowRight, Play } from 'lucide-react';
import { scenarios } from '../types';
interface Props {
  onView: (view: string) => void;
  onScenario: (scenario: string) => void;
  onSignIn: () => void;
  signedIn: boolean;
}
export function Overview({ onView, onScenario, onSignIn, signedIn }: Props) {
  return (
    <div className="overview-page">
      <section className="overview-feature">
        <div>
          <h2>Catches missed steps in hands-on procedures, automatically.</h2>
          <p>
            Show it the right way once. It checks every later recording and tells you what was
            skipped.
          </p>
          <div className="actions">
            <button className="button primary" onClick={() => onScenario('skipped-cap')}>
              <Play size={18} /> See it catch a mistake (30 seconds)
            </button>
            <button className="button" onClick={signedIn ? () => onView('Teach') : onSignIn}>
              Try it with your own video <ArrowRight size={18} />
            </button>
          </div>
        </div>
        <img
          src={`${import.meta.env.BASE_URL}images/procedure-studio.webp`}
          alt="Illustration of colored-water tubes; not camera footage"
          width="480"
          height="480"
        />
      </section>
      <section className="overview-section" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <div className="how-strip">
          <article className="panel">
            <h3>1 Teach</h3>
            <p>Upload one video of the right way.</p>
            <small>
              Muse Spark reads sampled video frames and writes the steps. Muse Voice Transcribe
              transcribes narration when audio is used.
            </small>
          </article>
          <article className="panel">
            <h3>2 Check</h3>
            <p>Upload another recording.</p>
            <small>
              SAM 3.1 finds the objects; the rules engine decides whether a step was observed.
            </small>
          </article>
          <article className="panel">
            <h3>3 Results</h3>
            <p>See each skipped or out-of-order step, with the frame and reason behind it.</p>
            <small>
              An open-weights model gives a second opinion when configured. The rules still decide.
            </small>
          </article>
        </div>
        <p className="field-help">
          The examples on this page are animated; no model ran for them. Accuracy on real procedure
          videos has not been measured.
        </p>
      </section>
      <section className="overview-section">
        <div className="section-heading">
          <h2>Try an animated example</h2>
          <span>Example runs</span>
        </div>
        <div className="sample-chips">
          {scenarios.map(([name, title]) => (
            <button className="button" key={name} onClick={() => onScenario(name)}>
              {title}
              <ArrowRight size={16} />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
