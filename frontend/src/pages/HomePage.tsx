import * as m from 'motion/react-m';
import { useReducedMotion, useScroll, useSpring } from 'motion/react';
import {
  ArrowRight,
  ArrowUpRight,
  Video,
  ListChecks,
  ScanLine,
  LockKeyhole,
  ExternalLink,
} from 'lucide-react';
import { Brand } from '../components/Brand';
import { ThemeToggle } from '../components/ThemeToggle';
import { MotionPreview } from '../components/MotionPreview';
import { useTheme } from '../hooks/ThemeContext';
import { motionTokens, springs } from '../lib/motion-tokens';

interface Props {
  onOpen: (scenario?: string, view?: string) => void;
}
const steps = [
  {
    n: '01',
    title: 'Teach the procedure',
    copy: 'Upload a video showing the right way. Review the steps Apprentice creates.',
    icon: Video,
  },
  {
    n: '02',
    title: 'Check another take',
    copy: 'Add a new recording of the same procedure. Follow its progress as objects and actions are checked.',
    icon: ScanLine,
  },
  {
    n: '03',
    title: 'Review the evidence',
    copy: 'Open each finding at its timestamp. See what was confirmed, what needs review, and why.',
    icon: ListChecks,
  },
];
export function HomePage({ onOpen }: Props) {
  const reduced = useReducedMotion();
  const { theme } = useTheme();
  const suffix = theme === 'dark' ? '-dark' : '';
  const { scrollYProgress } = useScroll();
  const reading = useSpring(scrollYProgress, springs.gentle);
  const entrance = {
    hidden: {},
    visible: { transition: { staggerChildren: motionTokens.stagger } },
  };
  const item = {
    hidden: { opacity: 0, y: reduced ? 0 : motionTokens.distance.md },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth },
    },
  };
  const reveal = {
    initial: reduced ? (false as const) : { opacity: 0, y: motionTokens.distance.lg },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.15 },
    transition: { duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth },
  };
  const teach = () => onOpen(undefined, 'Teach');
  return (
    <div className="home-page">
      <m.div
        className="page-read-progress"
        style={{ scaleX: reduced ? scrollYProgress : reading }}
        aria-hidden="true"
      />
      <a className="skip-link" href="#home-main">
        Skip to main content
      </a>
      <header className="home-nav">
        <a href="#" aria-label="Apprentice home">
          <Brand />
        </a>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#workspace-preview">The workspace</a>
          <ThemeToggle />
          <button className="nav-open" aria-label="Open Apprentice" onClick={() => onOpen()}>
            <span className="nav-open-label">Open Apprentice</span> <ArrowUpRight size={17} />
          </button>
        </nav>
      </header>
      <main id="home-main">
        <section className="home-hero">
          <m.div
            className="hero-copy"
            initial={reduced ? false : 'hidden'}
            animate="visible"
            variants={entrance}
          >
            <m.p variants={item} className="home-eyebrow">
              Video → procedure → evidence
            </m.p>
            <m.h1 aria-label="Show it once. Check each step." variants={entrance}>
              {['Show it once.', 'Check each step.'].map((line) => (
                <span className="hero-line" key={line}>
                  <m.span
                    variants={{
                      hidden: { y: reduced ? 0 : motionTokens.distance.heroLine, opacity: 0 },
                      visible: {
                        y: 0,
                        opacity: 1,
                        transition: {
                          duration: motionTokens.duration.slow,
                          ease: motionTokens.easing.smooth,
                        },
                      },
                    }}
                  >
                    {line}
                  </m.span>
                </span>
              ))}
            </m.h1>
            <m.p variants={item}>
              Turn a teaching video into a step-by-step checklist. Check later recordings for missed
              steps, then review the evidence behind each finding.
            </m.p>
            <m.div variants={item} className="hero-actions">
              <m.button
                whileHover={reduced ? undefined : { y: -motionTokens.distance.sm / 2 }}
                whileTap={reduced ? undefined : { scale: motionTokens.scale.press }}
                transition={springs.snappy}
                className="home-button"
                onClick={teach}
              >
                Teach a procedure <ArrowRight size={19} />
              </m.button>
              <a className="home-secondary" href="#how-it-works">
                See how it works
              </a>
            </m.div>
            <m.span variants={item} className="hero-privacy">
              <LockKeyhole size={15} /> Your recordings stay in your private workspace.
            </m.span>
          </m.div>
          <MotionPreview>
            <div className="product-window-bar">
              <span className="window-dot" />
              <span>Apprentice / Teach</span>
              <span>Workspace</span>
            </div>
            <img
              src={`${import.meta.env.BASE_URL}images/product-learn${suffix}.png?v=themes-20261101`}
              width="1505"
              height="1045"
              alt="Current Apprentice Teach workspace with a teaching-video upload and optional description"
              fetchPriority="high"
            />
            <div className="product-caption">
              <Video size={17} />
              <span>Start with your own recording.</span>
              <ArrowUpRight size={17} />
            </div>
          </MotionPreview>
        </section>
        <section className="home-method" id="how-it-works">
          <div className="home-section-heading">
            <m.h2 {...reveal}>
              One procedure.
              <br />A clearer next take.
            </m.h2>
            <m.p {...reveal}>
              For work that happens away from a keyboard. Show the intended actions, check the next
              recording, and keep a reviewable record.
            </m.p>
          </div>
          <div className="method-stages">
            {steps.map(({ n, title, copy, icon: Icon }, index) => (
              <m.article
                {...reveal}
                transition={{
                  ...reveal.transition,
                  delay: reduced ? 0 : index * motionTokens.stagger,
                }}
                key={n}
              >
                <div className="method-number">
                  <span>{n}</span>
                  <Icon size={24} />
                </div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </m.article>
            ))}
          </div>
        </section>
        <section className="home-workspace" id="workspace-preview">
          <m.div {...reveal} className="home-section-heading">
            <h2>
              Your videos.
              <br />
              Your workspace.
            </h2>
            <p>
              A place to teach, check, and return to the moments that matter. Start with a short
              recording and clearly distinguishable objects.
            </p>
          </m.div>
          <div className="workspace-shots">
            <m.button
              {...reveal}
              className="workspace-shot"
              onClick={teach}
              aria-label="Open Teach"
            >
              <img
                src={`${import.meta.env.BASE_URL}images/product-learn${suffix}.png?v=themes-20261101`}
                width="1505"
                height="1045"
                alt="Current teaching-video upload screen"
                loading="lazy"
              />
              <span>
                <strong>Teach</strong> Start with the right way. <ArrowUpRight size={18} />
              </span>
            </m.button>
            <m.button
              {...reveal}
              className="workspace-shot"
              onClick={() => onOpen(undefined, 'Check')}
              aria-label="Open Check"
            >
              <img
                src={`${import.meta.env.BASE_URL}images/product-check${suffix}.png?v=themes-20261101`}
                width="1505"
                height="1045"
                alt="Current Check screen guiding users to teach a procedure before checking another recording"
                loading="lazy"
              />
              <span>
                <strong>Check</strong> Compare the next recording. <ArrowUpRight size={18} />
              </span>
            </m.button>
          </div>
          <p className="home-interface-note">
            Current interface. Your recordings and results appear as you work.
          </p>
        </section>
        <section className="home-evidence">
          <m.div {...reveal}>
            <span className="home-eyebrow">A result you can inspect</span>
            <h2>See why a step was flagged.</h2>
            <p>
              Findings connect back to the recording. Review the expected step, inspect the visible
              evidence, and download a report with its event history.
            </p>
          </m.div>
          <m.div {...reveal} className="evidence-principles">
            <article>
              <span>01</span>
              <div>
                <h3>Jump to the moment</h3>
                <p>Select a finding to inspect its timestamp and object overlays.</p>
              </div>
            </article>
            <article>
              <span>02</span>
              <div>
                <h3>Know what needs review</h3>
                <p>
                  Unclear evidence stays unconfirmed. Model opinions are separate from rule
                  decisions.
                </p>
              </div>
            </article>
            <article>
              <span>03</span>
              <div>
                <h3>Keep the record</h3>
                <p>Download the report and verify its event log against a separately saved root.</p>
              </div>
            </article>
          </m.div>
        </section>
        <section className="home-close">
          <m.h2 {...reveal}>Start with the right way.</m.h2>
          <div className="home-close-row">
            <p>
              Sign in, upload your teaching video, and build the checklist for your next recording.
            </p>
            <button className="home-button" onClick={teach}>
              Teach a procedure <ArrowRight size={20} />
            </button>
          </div>
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
            Built in the open <ExternalLink size={15} />
          </a>
        </div>
        <p>Suggested steps. Visible evidence. Clear reasons.</p>
      </footer>
    </div>
  );
}
