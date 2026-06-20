import { interpolate, spring } from "remotion";
import type { Intensity } from "./schema";

type MotionPreset = {
  driftEnd: number; // scale at end of clip (continuous drift)
  punchFrom: number; // starting scale of a punch-in (settles to 1.0)
  damping: number; // spring damping for the punch settle
  fixedIntervalSec: number | null; // hype: extra punch-ins on a timer
};

const PRESETS: Record<Intensity, MotionPreset> = {
  gentle: { driftEnd: 1.05, punchFrom: 1.08, damping: 200, fixedIntervalSec: null },
  medium: { driftEnd: 1.08, punchFrom: 1.12, damping: 160, fixedIntervalSec: null },
  hype: { driftEnd: 1.12, punchFrom: 1.18, damping: 120, fixedIntervalSec: 4 },
};

export const presetFor = (intensity: Intensity): MotionPreset => PRESETS[intensity];

/**
 * Scale for the foreground clip at a given content-local frame:
 * continuous drift, multiplied by a spring punch-in from the most recent
 * cut point (and, for hype, fixed-interval punches).
 */
export const clipScale = (
  frame: number,
  durationInFrames: number,
  cutPointFrames: number[],
  intensity: Intensity,
  fps: number,
): number => {
  const p = presetFor(intensity);
  const drift = interpolate(frame, [0, durationInFrames], [1, p.driftEnd], {
    extrapolateRight: "clamp",
  });

  const points = [...cutPointFrames];
  if (p.fixedIntervalSec) {
    const step = Math.round(p.fixedIntervalSec * fps);
    for (let f = step; f < durationInFrames; f += step) points.push(f);
  }

  // most recent punch point at or before this frame
  const recent = points.filter((f) => f <= frame).sort((a, b) => b - a)[0];
  if (recent === undefined) return drift;

  const s = spring({
    frame: frame - recent,
    fps,
    config: { damping: p.damping, mass: 0.6, stiffness: 120 },
  });
  const punch = interpolate(s, [0, 1], [p.punchFrom, 1]);
  return drift * punch;
};
