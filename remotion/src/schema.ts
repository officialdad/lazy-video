import { z } from "zod";

export const captionSchema = z.object({
  start: z.number(),
  end: z.number(),
  text: z.string(),
});

export const brandSchema = z.object({
  caption_font: z.string(),
  caption_position: z.string(),
  caption_color: z.string(),
  caption_highlight_color: z.string(),
  caption_bg: z.string(),
  show_progress_bar: z.boolean(),
  bg_color: z.string().default("#0B132B"),
});

export const reelSchema = z.object({
  clipSrc: z.string(),
  introSrc: z.string(),
  outroSrc: z.string(),
  introDur: z.number(),
  clipDur: z.number(),
  outroDur: z.number(),
  title: z.string(),
  intensity: z.enum(["gentle", "medium", "hype"]),
  captions: z.array(captionSchema),
  cutPointsSec: z.array(z.number()),
  brand: brandSchema,
});

export type ReelProps = z.infer<typeof reelSchema>;
export type Caption = z.infer<typeof captionSchema>;
export type Intensity = ReelProps["intensity"];
