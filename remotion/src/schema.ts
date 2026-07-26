import { z } from "zod";

export const wordSchema = z.object({
  w: z.string(),
  start: z.number(),
  end: z.number(),
});

export const captionSchema = z.object({
  start: z.number(),
  end: z.number(),
  text: z.string(),
  words: z.array(wordSchema).default([]),
  /** Logical icon name (e.g. "package", "memory") -> looked up in Reel.tsx's
      CAPTION_ICONS map. "" = no icon. Kept as a short logical name, not an
      @mdi/js export name, so the EDL/schema stay decoupled from that package. */
  icon: z.string().default(""),
});

export const brandSchema = z.object({
  caption_font: z.string(),
  caption_uppercase: z.boolean().default(true),
  caption_max_words: z.number().default(4),
  caption_position: z.string(),
  caption_color: z.string(),
  caption_highlight_color: z.string(),
  caption_bg: z.string(),
  show_progress_bar: z.boolean(),
  bg_color: z.string().default("#0B132B"),
  /** "default" = today's behaviour (karaoke captions, fade/slide-in text)
      unchanged. "typewriter" = all on-screen text types on character-by-
      character with a blinking cursor (see remotion/src/typewriter.ts). */
  text_animation: z.enum(["default", "typewriter"]).default("default"),
});

export const ctaSchema = z.object({
  text: z.string(),
  durationSec: z.number(),
});

/** Attention overlay: an animated MDI arrow or a pulsing highlight box.
    x/y (and w/h for highlight) are % of the output frame; times are clip-local. */
export const overlaySchema = z.object({
  type: z.enum(["arrow", "highlight"]),
  start: z.number(),
  end: z.number(),
  x: z.number(),
  y: z.number(),
  w: z.number().default(0),
  h: z.number().default(0),
  dir: z.enum(["up", "down"]).default("down"),
});

/** End card: a title + icon/label list shown over the payoff photo beat.
    icon fields are logical names (see captionSchema.icon) resolved in Reel.tsx's
    CAPTION_ICONS map -- "" = no icon, same contract as captions. */
export const endCardSchema = z.object({
  title: z.string(),
  icon: z.string().default(""),                 // ceremony accent icon (logical name)
  items: z.array(z.object({
    icon: z.string().default(""),               // logical name
    label: z.string(),
  })),
});

/** Still-card intro: hero product photo + hook text (+ optional small logo
    chip), staged via stage_asset (basename only). null = no card intro (falls
    back to the introSrc video path, if any). */
export const introCardSchema = z.object({
  image: z.string().default(""),  // staticFile basename of the hero photo; "" = no image
  logo: z.string().default(""),   // staticFile basename of a small logo chip; "" = no logo
  text: z.string(),
});

export const reelSchema = z.object({
  clipSrc: z.string(),
  introSrc: z.string(),
  introDur: z.number(),
  /** Card intro (logo + hook text); takes precedence over introSrc when set. */
  introCard: introCardSchema.nullable().default(null),
  clipDur: z.number(),
  title: z.string(),
  intensity: z.enum(["gentle", "medium", "hype"]),
  captions: z.array(captionSchema),
  overlays: z.array(overlaySchema).default([]),
  /** Payoff photo held after the content clip, before the CTA. "" = no photo beat. */
  endImage: z.string().default(""),
  endImageDur: z.number().default(0),
  /** Optional title + icon/label list shown over the endImage photo beat. null = none. */
  endCard: endCardSchema.nullable().default(null),
  cutPointsSec: z.array(z.number()),
  cta: ctaSchema,
  brand: brandSchema,
  bgMusic: z.string().default(""),
  bgMusicVolume: z.number().default(0.15),
  /** Seconds to skip at the start of the music file (e.g. past a dead intro). */
  bgMusicOffset: z.number().default(0),
  coverBg: z.boolean().default(true),
});

export type ReelProps = z.infer<typeof reelSchema>;
export type Caption = z.infer<typeof captionSchema>;
export type Word = z.infer<typeof wordSchema>;
export type Overlay = z.infer<typeof overlaySchema>;
export type EndCard = z.infer<typeof endCardSchema>;
export type IntroCard = z.infer<typeof introCardSchema>;
export type Intensity = ReelProps["intensity"];
