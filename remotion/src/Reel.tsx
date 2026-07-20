import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { mdiArrowDownBold, mdiArrowUpBold, mdiGestureSwipeLeft } from "@mdi/js";
import { Captions } from "./Captions";
import { CAPTION_FONT } from "./fonts";
import { clipScale } from "./motion";
import type { Overlay, ReelProps } from "./schema";

const src = (p: string) => (p.startsWith("http") ? p : staticFile(p));

/** Bouncing MDI arrow directing attention up or down; x/y are % of the frame. */
const ArrowOverlay: React.FC<{ o: Overlay; color: string }> = ({ o, color }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 } });
  const bob = Math.sin((frame / fps) * Math.PI * 2 * 1.4) * 16; // gentle 1.4 Hz bounce
  const along = o.dir === "up" ? -bob : bob;
  return (
    <div
      style={{
        position: "absolute",
        left: `${o.x}%`,
        top: `${o.y}%`,
        transform: `translate(-50%, -50%) translateY(${along}px) scale(${interpolate(pop, [0, 1], [0.3, 1])})`,
      }}
    >
      <svg viewBox="0 0 24 24" width={130} height={130}>
        <path
          d={o.dir === "up" ? mdiArrowUpBold : mdiArrowDownBold}
          fill={color}
          stroke="rgba(0,0,0,0.6)"
          strokeWidth={0.6}
        />
      </svg>
    </div>
  );
};

/** Pulsing outline drawing attention to a screen region; x/y/w/h are % of the frame. */
const HighlightOverlay: React.FC<{ o: Overlay; color: string }> = ({ o, color }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 } });
  const pulse = 0.55 + 0.45 * Math.abs(Math.sin((frame / fps) * Math.PI * 1.6));
  return (
    <div
      style={{
        position: "absolute",
        left: `${o.x}%`,
        top: `${o.y}%`,
        width: `${o.w}%`,
        height: `${o.h}%`,
        border: `6px solid ${color}`,
        borderRadius: 16,
        boxShadow: `0 0 26px ${color}88, inset 0 0 26px ${color}44`,
        opacity: pulse * pop,
        transform: `scale(${interpolate(pop, [0, 1], [1.15, 1])})`,
      }}
    />
  );
};

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
      {/* blurred cover background -- only when the clip doesn't fill the 9:16 frame
          (a matched-aspect clip fully covers it, so this would just be a wasted decode) */}
      {props.coverBg ? (
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
      ) : null}

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
        maxWords={props.brand.caption_max_words}
      />

      {/* attention overlays (arrows / highlight boxes) at clip-local times */}
      {(props.overlays ?? []).map((o, i) => (
        <Sequence
          key={i}
          from={Math.round(o.start * fps)}
          durationInFrames={Math.max(1, Math.round((o.end - o.start) * fps))}
        >
          {o.type === "arrow" ? (
            <ArrowOverlay o={o} color={props.brand.caption_highlight_color} />
          ) : (
            <HighlightOverlay o={o} color={props.brand.caption_highlight_color} />
          )}
        </Sequence>
      ))}

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
        <svg
          viewBox="0 0 24 24"
          width={150}
          height={150}
          style={{ transform: `scale(${interpolate(arrowPop, [0, 1], [0.4, 1])})` }}
        >
          <path d={mdiGestureSwipeLeft} fill={brand.caption_highlight_color} />
        </svg>
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

/** The payoff photo: held for its full duration with a slow ken-burns push-in. */
const EndImageCard: React.FC<{ image: string; durationInFrames: number }> = ({
  image,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
      <Img
        src={src(image)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale})`,
        }}
      />
    </AbsoluteFill>
  );
};

export const Reel: React.FC<ReelProps> = (props) => {
  const { fps, durationInFrames } = useVideoConfig();
  const introF = Math.round(props.introDur * fps);
  const clipF = Math.round(props.clipDur * fps);
  const ctaF = Math.round(props.cta.durationSec * fps);
  const endF = props.endImage ? Math.round(props.endImageDur * fps) : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: props.brand.bg_color }}>
      {/* background music under the whole reel, fading in/out */}
      {props.bgMusic ? (
        <Audio
          src={src(props.bgMusic)}
          loop
          trimBefore={Math.round(props.bgMusicOffset * fps)}
          volume={(f) =>
            interpolate(
              f,
              [0, 12, durationInFrames - 18, durationInFrames],
              [0, props.bgMusicVolume, props.bgMusicVolume, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            )
          }
        />
      ) : null}

      {introF > 0 && props.introSrc ? (
        <Sequence durationInFrames={introF}>
          <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
            <OffthreadVideo src={src(props.introSrc)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </AbsoluteFill>
        </Sequence>
      ) : null}

      <Sequence from={introF} durationInFrames={clipF}>
        <ContentClip {...props} />
      </Sequence>

      {endF > 0 ? (
        <Sequence from={introF + clipF} durationInFrames={endF}>
          <EndImageCard image={props.endImage} durationInFrames={endF} />
        </Sequence>
      ) : null}

      <Sequence from={introF + clipF + endF} durationInFrames={ctaF}>
        <CtaCard text={props.cta.text} brand={props.brand} />
      </Sequence>
    </AbsoluteFill>
  );
};
