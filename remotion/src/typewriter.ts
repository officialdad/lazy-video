/**
 * Shared typewriter text-reveal helpers, used only when
 * `brand.text_animation === "typewriter"` (Captions.tsx / Reel.tsx). Every
 * on-screen text element types on character-by-character with a blinking
 * block cursor, sized off its own on-screen duration -- there is no fixed
 * global typing speed. When text_animation is "default" none of this runs;
 * that path is untouched.
 */

/** Block cursor glyph; callers colour it with brand.caption_highlight_color. */
export const CURSOR_GLYPH = "▋";

// Type across ~60% of the element's on-screen window, holding the rest --
// keeps typing inside the requested 55-65% band without per-caller tuning.
const DEFAULT_TYPE_FRACTION = 0.6;
const CURSOR_BLINK_FRAMES = 15;
// Keep blinking this long (in frames) after typing completes, then hide for good.
const CURSOR_HOLD_FRAMES = 20;

/** Chars/frame so `totalChars` finish typing in roughly `typeFraction` of
    `durationInFrames` -- the element's own on-screen duration, passed in by
    the caller (caption cue length, intro/CTA durationInFrames, an end-card
    item's slot). Never hardcode a speed that assumes a fixed duration. */
export const charsPerFrameFor = (
  totalChars: number,
  durationInFrames: number,
  typeFraction: number = DEFAULT_TYPE_FRACTION,
): number => {
  if (totalChars <= 0 || durationInFrames <= 0) return 0;
  const typingWindowFrames = Math.max(1, durationInFrames * typeFraction);
  return totalChars / typingWindowFrames;
};

/** How many characters are visible at `frame`, given typing starts at
    `startFrame` and advances at `charsPerFrame`. Clamped to [0, totalChars]. */
export const typedCount = (
  frame: number,
  startFrame: number,
  totalChars: number,
  charsPerFrame: number,
): number => {
  if (totalChars <= 0 || charsPerFrame <= 0) return 0;
  const elapsed = frame - startFrame;
  if (elapsed <= 0) return 0;
  return Math.min(totalChars, Math.floor(elapsed * charsPerFrame));
};

/** Blinking block cursor: toggles every ~15 frames while typing, keeps
    blinking for a short moment after the text finishes, then hides for good. */
export const cursorVisible = (
  frame: number,
  startFrame: number,
  totalChars: number,
  charsPerFrame: number,
): boolean => {
  const elapsed = frame - startFrame;
  if (elapsed < 0 || charsPerFrame <= 0) return false;
  const typingFrames = totalChars / charsPerFrame;
  if (elapsed > typingFrames + CURSOR_HOLD_FRAMES) return false;
  return Math.floor(elapsed / CURSOR_BLINK_FRAMES) % 2 === 0;
};

/** One chunk of text after the typing budget has been applied: how much of
    it is shown, and whether it's the chunk the cursor currently sits inside
    (still typing, or just finished -- stays "current" until the next chunk
    starts revealing). Generic over `meta` so callers can carry per-chunk
    styling (a caption word's colour, a hook-text segment's highlight flag). */
export type TypedChunk<T> = { shown: string; isCurrent: boolean; meta: T };

/** Walks a running character budget (`typed`, from typedCount) across an
    ordered list of text chunks -- e.g. a caption's words, or a hook line's
    highlight/base segments -- revealing each fully, partially, or not at
    all, so per-chunk colouring survives typing (a chunk may show only its
    first k characters). */
export const revealChunks = <T,>(
  chunks: { text: string; meta: T }[],
  typed: number,
): TypedChunk<T>[] => {
  let budget = typed;
  return chunks.map(({ text, meta }) => {
    const shown = text.slice(0, Math.max(0, budget));
    const isCurrent = budget > 0 && budget <= text.length;
    budget -= text.length;
    return { shown, isCurrent, meta };
  });
};
