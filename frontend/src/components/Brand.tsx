export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand ${compact ? 'brand-compact' : ''}`}>
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
        <rect
          x="3"
          y="3"
          width="23"
          height="23"
          rx="5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path
          d="m9 15 4 4 9-9M3 9h5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>apprentice</span>
    </span>
  );
}
