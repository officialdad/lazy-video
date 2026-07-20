import React from "react";
import { Composition } from "remotion";
import { Reel } from "./Reel";
import { reelSchema, type ReelProps } from "./schema";

const DEFAULT_BRAND = {
  caption_font: "Anton",
  caption_uppercase: true,
  caption_max_words: 4,
  caption_position: "bottom-third",
  caption_color: "#ffffff",
  caption_highlight_color: "#ffd400",
  caption_bg: "rgba(0,0,0,0.55)",
  show_progress_bar: true,
  bg_color: "#0B132B",
};

// Preview defaults; the real values are injected per-render via --props.
const DEFAULT_PROPS: ReelProps = {
  clipSrc: "01_rm80-boleh-buat-apa.mp4",
  introSrc: "",
  introDur: 0,
  clipDur: 6,
  title: "RM80 Boleh Buat Apa?",
  intensity: "gentle",
  cutPointsSec: [0],
  captions: [
    {
      start: 0,
      end: 3,
      text: "Assalamualaikum semua",
      words: [
        { w: "Assalamualaikum", start: 0.2, end: 1.4 },
        { w: "semua", start: 1.4, end: 2.2 },
      ],
    },
  ],
  overlays: [],
  endImage: "",
  endImageDur: 0,
  cta: { text: "FOLLOW & STAY TUNED", durationSec: 1.6 },
  brand: DEFAULT_BRAND,
  bgMusic: "",
  bgMusicVolume: 0.15,
  coverBg: true,
};

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Reel"
      component={Reel}
      schema={reelSchema}
      defaultProps={DEFAULT_PROPS}
      fps={FPS}
      width={1080}
      height={1920}
      durationInFrames={Math.round((0 + 6 + 1.6) * FPS)}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.round(
          (props.introDur + props.clipDur + props.endImageDur + props.cta.durationSec) * FPS,
        ),
        fps: FPS,
        width: 1080,
        height: 1920,
      })}
    />
  );
};
