import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Captions } from "./Captions";
import { CAPTION_FONT } from "./fonts";
import { clipScale } from "./motion";
import type { ReelProps } from "./schema";

const src = (p: string) => (p.startsWith("http") ? p : staticFile(p));

/** The content clip: blurred cover background + sharp contained foreground with motion. */
const ContentClip: React.FC<ReelProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const cutPointFrames = props.cutPointsSec.map((s) => Math.round(s * fps));
  const scale = clipScale(frame, durationInFrames, cutPointFrames, props.intensity, fps);

  const titleSpring = spring({ frame, fps, config: { damping: 200 } });
  const titleOpacity = interpolate(frame, [0, 12, fps * 2.2, fps * 2.8], [0, 1, 1, 0], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(titleSpring, [0, 1], [40, 0]);
  const contentProgress = interpolate(frame, [0, durationInFrames], [0, 1]);

  return (
    <AbsoluteFill style={{ backgroundColor: props.brand.bg_color }}>
      {/* blurred cover background */}
      <AbsoluteFill>
        <OffthreadVideo
          src={src(props.clipSrc)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "blur(36px) brightness(0.45)",
            transform: "scale(1.15)",
          }}
          muted
        />
      </AbsoluteFill>

      {/* sharp contained foreground with drift + punch-in */}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <OffthreadVideo
          src={src(props.clipSrc)}
          style={{ width: "100%", objectFit: "contain", transform: `scale(${scale})` }}
        />
      </AbsoluteFill>

      {/* hook title lower-third, fades after the opening */}
      {props.title ? (
        <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center", paddingTop: "12%" }}>
          <div
            style={{
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              fontFamily: CAPTION_FONT,
              fontWeight: 400,
              fontSize: 88,
              letterSpacing: 1,
              color: props.brand.caption_color,
              background: props.brand.caption_bg,
              padding: "16px 40px",
              borderRadius: 22,
              textAlign: "center",
              maxWidth: "88%",
              textShadow: "0 3px 10px rgba(0,0,0,0.5)",
            }}
          >
            {props.brand.caption_uppercase ? props.title.toUpperCase() : props.title}
          </div>
        </AbsoluteFill>
      ) : null}

      <Captions
        captions={props.captions}
        color={props.brand.caption_color}
        highlight={props.brand.caption_highlight_color}
        bg={props.brand.caption_bg}
        position={props.brand.caption_position}
        uppercase={props.brand.caption_uppercase}
      />

      {/* thin progress bar */}
      {props.brand.show_progress_bar ? (
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 8, background: "rgba(255,255,255,0.15)" }}>
          <div style={{ height: "100%", width: `${contentProgress * 100}%`, background: props.brand.caption_highlight_color }} />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Swipe-left CTA card: a brand panel slides in from the right (replaces the outro). */
const CtaCard: React.FC<{ text: string; brand: ReelProps["brand"] }> = ({ text, brand }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200, mass: 0.7, stiffness: 90 } });
  const x = interpolate(enter, [0, 1], [width, 0]); // from offscreen-right to 0 = swipe left
  const arrowPop = spring({ frame: frame - 6, fps, config: { damping: 200 } });

  return (
    <AbsoluteFill style={{ transform: `translateX(${x}px)`, backgroundColor: brand.bg_color }}>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 28 }}>
        <div style={{ fontSize: 120, transform: `scale(${interpolate(arrowPop, [0, 1], [0.4, 1])})` }}>👉</div>
        <div
          style={{
            fontFamily: CAPTION_FONT,
            fontWeight: 400,
            fontSize: 110,
            letterSpacing: 2,
            color: brand.caption_color,
            textAlign: "center",
            maxWidth: "84%",
            lineHeight: 1.05,
            textShadow: "0 4px 14px rgba(0,0,0,0.5)",
          }}
        >
          {text.toUpperCase()}
        </div>
        <div style={{ width: 220, height: 10, borderRadius: 6, background: brand.caption_highlight_color }} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Reel: React.FC<ReelProps> = (props) => {
  const { fps } = useVideoConfig();
  const introF = Math.round(props.introDur * fps);
  const clipF = Math.round(props.clipDur * fps);
  const ctaF = Math.round(props.cta.durationSec * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: props.brand.bg_color }}>
      <Sequence durationInFrames={introF}>
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <OffthreadVideo src={src(props.introSrc)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </AbsoluteFill>
      </Sequence>

      <Sequence from={introF} durationInFrames={clipF}>
        <ContentClip {...props} />
      </Sequence>

      <Sequence from={introF + clipF} durationInFrames={ctaF}>
        <CtaCard text={props.cta.text} brand={props.brand} />
      </Sequence>
    </AbsoluteFill>
  );
};
