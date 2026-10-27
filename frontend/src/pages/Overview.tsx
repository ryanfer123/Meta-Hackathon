import { ArrowRight, Check, FileVideo, LockKeyhole } from 'lucide-react';
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
          <h2>
            One procedure.
            <br />
            Every step in view.
          </h2>
          <p>
            Begin with a sample run. Inspect an observation, follow its predicate, and take the
            evidence into an audit.
          </p>
          <button className="button primary" onClick={() => onScenario('skipped-cap')}>
            Inspect the skipped cap <ArrowRight size={18} />
          </button>
        </div>
        <img
          src={`${import.meta.env.BASE_URL}images/procedure-studio.webp`}
          alt="Illustrative colored-water procedure setup"
          width="480"
          height="480"
        />
      </section>
      <section className="overview-section">
        <div className="section-heading">
          <h2>Try a different take</h2>
          <span>Synthetic replay</span>
        </div>
        <div className="scenario-list">
          {scenarios.map(([name, title]) => (
            <button key={name} onClick={() => onScenario(name)}>
              <span className={name === 'clean' ? 'scenario-dot clean' : 'scenario-dot'} />
              <span>{title}</span>
              <ArrowRight size={18} />
            </button>
          ))}
        </div>
      </section>
      <div className="overview-bottom">
        <section>
          <FileVideo size={27} />
          <h3>Bring your own recording.</h3>
          <p>
            The Learn view is ready for an expert take. Cloud storage keeps your source files; the
            Python inference service compiles the protocol when connected.
          </p>
          <button className="text-button" onClick={() => onView('Learn')}>
            Open Learn <ArrowRight size={17} />
          </button>
        </section>
        <section>
          <LockKeyhole size={27} />
          <h3>{signedIn ? 'A private place for your work.' : 'Keep the useful runs.'}</h3>
          <p>
            Save a run to your library and revisit the same evidence later. Your recordings and
            saved work are scoped to your account.
          </p>
          <button
            className="text-button"
            onClick={signedIn ? () => onView('Run library') : onSignIn}
          >
            {signedIn ? 'Open your library' : 'Sign in to save'} <ArrowRight size={17} />
          </button>
        </section>
      </div>
      <p className="scope-note">
        <Check size={17} />
        Synthetic examples demonstrate software behavior. Real-video accuracy remains unmeasured.
      </p>
    </div>
  );
}
