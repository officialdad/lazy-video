import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Caption } from "./schema";

type Props = {
  captions: Caption[];
  font: string;
  color: string;
  highlight: string;
  bg: string;
  position: string;
};

/**
 * Phrase-synced captions with per-word highlight. We only have phrase-level
 * timestamps, so each word's highlight time is interpolated evenly across the
 * cue's duration -- gives a karaoke feel without per-word data.
 */
export const Captions: React.FC<Props> = ({ captions, font, color, highlight, bg, position }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const active = captions.find((c) => t >= c.start && t <= c.end);
  if (!active) return null;

  const words = active.text.split(/\s+/);
  const span = Math.max(active.end - active.start, 0.001);
  const progressed = (t - active.start) / span;
  const litCount = Math.floor(progressed * words.length + 0.0001);

  const pop = spring({
    frame: frame - Math.round(active.start * fps),
    fps,
    config: { damping: 200, mass: 0.5, stiffness: 140 },
  });
  const scale = interpolate(pop, [0, 1], [0.92, 1]);
  const opacity = interpolate(pop, [0, 1], [0, 1]);

  const bottom = position === "bottom-third" ? "26%" : "8%";

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom,
        display: "flex",
        justifyContent: "center",
        padding: "0 80px",
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          background: bg,
          borderRadius: 28,
          padding: "24px 36px",
          maxWidth: "90%",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "0 16px",
          boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
        }}
      >
        {words.map((w, i) => (
          <span
            key={i}
            style={{
              fontFamily: font,
              fontWeight: 800,
              fontSize: 64,
              lineHeight: 1.15,
              color: i <= litCount ? highlight : color,
              textShadow: "0 2px 6px rgba(0,0,0,0.5)",
              transition: "none",
            }}
          >
            {w}
          </span>
        ))}
      </div>
    </div>
  );
};
