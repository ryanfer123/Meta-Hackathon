'use client';
import * as m from 'motion/react-m';
import { useMotionValue, useSpring, useReducedMotion } from 'motion/react';
import type { ReactNode, PointerEvent } from 'react';
import { motionTokens, springs, shouldAnimate } from '../lib/motion-tokens';
export function MotionPreview({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  const x = useMotionValue(0),
    y = useMotionValue(0);
  const rotateX = useSpring(x, springs.gentle),
    rotateY = useSpring(y, springs.gentle);
  function move(event: PointerEvent<HTMLDivElement>) {
    if (
      reduced ||
      !shouldAnimate() ||
      event.pointerType !== 'mouse' ||
      !window.matchMedia('(hover: hover) and (pointer: fine)').matches
    )
      return;
    const box = event.currentTarget.getBoundingClientRect();
    x.set((-(event.clientY - box.top - box.height / 2) / box.height) * motionTokens.tilt * 2);
    y.set(((event.clientX - box.left - box.width / 2) / box.width) * motionTokens.tilt * 2);
  }
  return (
    <m.div
      className="hero-product"
      initial={reduced ? false : { opacity: 0, y: motionTokens.distance.lg }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth }}
      style={
        reduced ? undefined : { rotateX, rotateY, transformPerspective: motionTokens.perspective }
      }
      onPointerMove={move}
      onPointerLeave={() => {
        x.set(0);
        y.set(0);
      }}
    >
      {children}
    </m.div>
  );
}
