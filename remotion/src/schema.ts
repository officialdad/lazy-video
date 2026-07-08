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
});

export const ctaSchema = z.object({
  text: z.string(),
  durationSec: z.number(),
});

export const reelSchema = z.object({
  clipSrc: z.string(),
  introSrc: z.string(),
  introDur: z.number(),
  clipDur: z.number(),
  title: z.string(),
  intensity: z.enum(["gentle", "medium", "hype"]),
  captions: z.array(captionSchema),
  cutPointsSec: z.array(z.number()),
  cta: ctaSchema,
  brand: brandSchema,
  bgMusic: z.string().default(""),
  bgMusicVolume: z.number().default(0.15),
  coverBg: z.boolean().default(true),
});

export type ReelProps = z.infer<typeof reelSchema>;
export type Caption = z.infer<typeof captionSchema>;
export type Word = z.infer<typeof wordSchema>;
export type Intensity = ReelProps["intensity"];
