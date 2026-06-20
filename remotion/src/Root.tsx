import React from "react";
import { Composition } from "remotion";
import { Reel } from "./Reel";
import { reelSchema, type ReelProps } from "./schema";

const DEFAULT_BRAND = {
  caption_font: "Inter",
  caption_position: "bottom-third",
  caption_color: "#ffffff",
  caption_highlight_color: "#ffd400",
  caption_bg: "rgba(0,0,0,0.55)",
  show_progress_bar: true,
  bg_color: "#0B132B",
};

// Preview defaults; the real values are injected per-render via --props.
const DEFAULT_PROPS: ReelProps = {
  clipSrc: "output/test/clips/01_rm80-boleh-buat-apa.mp4",
  introSrc: "assets/intro.mp4",
  outroSrc: "assets/outro.mp4",
  introDur: 2,
  clipDur: 8,
  outroDur: 2.5,
  title: "RM80 Boleh Buat Apa?",
  intensity: "gentle",
  cutPointsSec: [0],
  captions: [{ start: 0, end: 3, text: "Assalamualaikum semua" }],
  brand: DEFAULT_BRAND,
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
      durationInFrames={Math.round((2 + 8 + 2.5) * FPS)}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.round((props.introDur + props.clipDur + props.outroDur) * FPS),
        fps: FPS,
        width: 1080,
        height: 1920,
      })}
    />
  );
};
