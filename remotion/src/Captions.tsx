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
  maxWords: number;
  /** Logical icon name -> MDI path data (see Reel.tsx's CAPTION_ICONS). */
  iconMap: Record<string, string>;
};

const CAPTION_FONT_SIZE = 84;
const CAPTION_ICON_SIZE = Math.round(CAPTION_FONT_SIZE * 1.2);

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

/** Split a word list into balanced lines of at most maxWords (avoids a lone trailing word). */
const toLines = (words: Word[], maxWords: number): Word[][] => {
  if (words.length <= maxWords) return [words];
  const numLines = Math.ceil(words.length / maxWords);
  const per = Math.ceil(words.length / numLines);
  const lines: Word[][] = [];
  for (let i = 0; i < words.length; i += per) lines.push(words.slice(i, i + per));
  return lines;
};

/**
 * Karaoke build-up with a consistent word count: each cue is split into balanced
 * lines of <= maxWords. Only the line containing the currently-spoken word shows,
 * its words revealed one-by-one at their spoken time, current word highlighted.
 * Keeps a steady, readable number of words on screen instead of whole sentences.
 */
export const Captions: React.FC<Props> = ({ captions, color, highlight, bg, position, uppercase, maxWords, iconMap }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const active = captions.find((c) => t >= c.start && t <= c.end);
  if (!active) return null;

  // unknown/empty icon name -> no icon, never a throw
  const iconPath = active.icon ? iconMap[active.icon] : undefined;

  const allWords = active.words?.length ? active.words : fallbackWords(active);
  const spokenCount = allWords.filter((w) => t >= w.start).length;
  if (!spokenCount) return null;
  const globalCurrent = spokenCount - 1;

  // pick the line holding the current word; build up within it
  const lines = toLines(allWords, Math.max(1, maxWords));
  let offset = 0;
  let words = lines[0];
  let currentIdx = 0;
  for (const line of lines) {
    if (globalCurrent < offset + line.length) {
      words = line;
      currentIdx = globalCurrent - offset;
      break;
    }
    offset += line.length;
  }
  words = words.slice(0, currentIdx + 1); // build-up: only revealed words in this line

  // accept a raw "NN%" for exact placement; else named presets
  const bottom = position.endsWith("%") ? position : position === "bottom-third" ? "26%" : "8%";

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
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          gap: 10,
          boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
        }}
      >
        {/* icon rides inside the same card as the words -- appears/disappears with
            it rather than animating on its own; no icon if the caption has none or
            names one this build doesn't recognise. */}
        {iconPath ? (
          <svg viewBox="0 0 24 24" width={CAPTION_ICON_SIZE} height={CAPTION_ICON_SIZE}>
            <path d={iconPath} fill={highlight} />
          </svg>
        ) : null}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            alignItems: "center",
            gap: "6px 18px",
          }}
        >
          {words.map((word, i) => {
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
                  fontSize: CAPTION_FONT_SIZE,
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
    </div>
  );
};
