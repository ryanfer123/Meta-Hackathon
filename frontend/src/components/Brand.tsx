export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand ${compact ? 'brand-compact' : ''}`}>
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
        <path d="M15 5 25 23H5Z" fill="none" stroke="currentColor" strokeWidth="2.2" />
        <circle cx="15" cy="5" r="4" fill="currentColor" />
        <circle cx="25" cy="23" r="4" fill="currentColor" />
        <circle cx="5" cy="23" r="4" fill="currentColor" />
      </svg>
      <span>apprentice</span>
    </span>
  );
}
