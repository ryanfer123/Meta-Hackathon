'use client';
import * as m from 'motion/react-m';
import { AnimatePresence, useReducedMotion } from 'motion/react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../hooks/ThemeContext';
import { motionTokens } from '../lib/motion-tokens';
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const reduced = useReducedMotion();
  return (
    <button
      className={`theme-toggle${compact ? ' is-compact' : ''}`}
      onClick={toggle}
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      aria-pressed={theme === 'dark'}
    >
      <AnimatePresence mode="wait" initial={false}>
        <m.span
          key={theme}
          initial={{ opacity: 0, rotate: reduced ? 0 : -35 }}
          animate={{ opacity: 1, rotate: 0 }}
          exit={{ opacity: 0, rotate: reduced ? 0 : 35 }}
          transition={{ duration: motionTokens.duration.fast }}
        >
          {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
        </m.span>
      </AnimatePresence>
      {!compact && (
        <span className="theme-toggle-label">{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
      )}
    </button>
  );
}
