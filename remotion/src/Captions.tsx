import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CAPTION_FONT } from "./fonts";
import type { Caption, Word } from "./schema";

type Props = {
  captions: Caption[];
  color: string;
  highlight: string;
  bg: string;
  position: string;
  uppercase: boolean;
};

/** Even fallback timing when a cue has no per-word data. */
const fallbackWords = (cap: Caption): Word[] => {
  const toks = cap.text.split(/\s+/).filter(Boolean);
  const span = Math.max(cap.end - cap.start, 0.001);
  return toks.map((w, i) => ({
    w,
    start: cap.start + (span * i) / toks.length,
    end: cap.start + (span * (i + 1)) / toks.length,
  }));
};

/**
 * Karaoke build-up: within the active cue, words appear one-by-one exactly when
 * spoken (per-word timestamps) and accumulate; the current word is highlighted.
 * Words not yet spoken are not shown -- keeps the line short and synced to voice.
 */
export const Captions: React.FC<Props> = ({ captions, color, highlight, bg, position, uppercase }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const active = captions.find((c) => t >= c.start && t <= c.end);
  if (!active) return null;

  const words = active.words?.length ? active.words : fallbackWords(active);
  const revealed = words.filter((w) => t >= w.start);
  if (!revealed.length) return null;
  const currentIdx = revealed.length - 1;

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
        padding: "0 70px",
      }}
    >
      <div
        style={{
          background: bg,
          borderRadius: 24,
          padding: "20px 34px",
          maxWidth: "92%",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: "6px 18px",
          boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
        }}
      >
        {revealed.map((word, i) => {
          const pop = spring({
            frame: frame - Math.round(word.start * fps),
            fps,
            config: { damping: 200, mass: 0.4, stiffness: 160 },
          });
          const scale = interpolate(pop, [0, 1], [0.6, 1]);
          const opacity = interpolate(pop, [0, 1], [0, 1]);
          const isCurrent = i === currentIdx;
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                transform: `scale(${isCurrent ? scale : 1})`,
                opacity,
                fontFamily: CAPTION_FONT,
                fontWeight: 400,
                fontSize: 84,
                letterSpacing: 1,
                lineHeight: 1.05,
                color: isCurrent ? highlight : color,
                textShadow: "0 3px 8px rgba(0,0,0,0.55)",
              }}
            >
              {uppercase ? word.w.toUpperCase() : word.w}
            </span>
          );
        })}
      </div>
    </div>
  );
};
