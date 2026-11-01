export const motionTokens = {
  duration: { fast: 0.18, normal: 0.35, slow: 0.65 },
  easing: { smooth: [0.22, 1, 0.36, 1] as const },
  distance: { sm: 8, md: 16, lg: 24, heroLine: '110%' },
  stagger: 0.08,
  tilt: 3,
  perspective: 1100,
  scale: { press: 0.98 },
};
export const springs = {
  gentle: { type: 'spring' as const, stiffness: 140, damping: 24, mass: 0.8 },
  snappy: { type: 'spring' as const, stiffness: 380, damping: 34 },
};
export function shouldAnimate() {
  return (
    typeof window !== 'undefined' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}
