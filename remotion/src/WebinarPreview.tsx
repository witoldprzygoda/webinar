import "@fontsource/manrope/400.css";
import "@fontsource/manrope/700.css";
import "@fontsource/jetbrains-mono/400.css";

import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
} from "remotion";
import type {
  NarrationFragment,
  PreviewProps,
  PreviewTimingBeat,
  SceneElement,
  ScenePlanScene,
} from "./types";

const COLORS = {
  background: "#0b1020",
  panel: "#131a2c",
  panelSoft: "#182137",
  text: "#f4f7fb",
  muted: "#9ba8bd",
  accent: "#6ee7f2",
  accentSoft: "rgba(110, 231, 242, 0.18)",
  border: "rgba(255, 255, 255, 0.12)",
  code: "#dbeafe",
  output: "#b8f7d4",
  warning: "#ffd48a",
};

const findActiveScene = (props: PreviewProps, frame: number) => {
  return props.timing.scenes.find(
    (scene) => frame >= scene.start_frame && frame < scene.end_frame,
  );
};

const findActiveBeat = (props: PreviewProps, frame: number) => {
  return props.timing.beats.find(
    (beat) => frame >= beat.start_frame && frame < beat.end_frame,
  );
};

const firstRevealFrame = (
  elementId: string,
  sceneId: string,
  beats: PreviewTimingBeat[],
): number | null => {
  const row = beats.find(
    (beat) => beat.scene_id === sceneId && beat.reveals.includes(elementId),
  );
  return row ? row.start_frame : null;
};

const elementOpacity = (
  frame: number,
  revealFrame: number | null,
  focused: boolean,
  anyFocus: boolean,
) => {
  if (revealFrame === null || frame < revealFrame) {
    return 0;
  }
  const appeared = interpolate(frame, [revealFrame, revealFrame + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const attention = anyFocus && !focused ? 0.58 : 1;
  return appeared * attention;
};

const ElementCard: React.FC<{
  element: SceneElement;
  frame: number;
  revealFrame: number | null;
  focused: boolean;
  anyFocus: boolean;
}> = ({element, frame, revealFrame, focused, anyFocus}) => {
  const codeLike = element.kind === "code" || element.kind === "output";
  const labelLike = element.kind === "label" || element.kind === "panel";
  const opacity = elementOpacity(frame, revealFrame, focused, anyFocus);
  const scale = focused
    ? interpolate(frame, [0, 8], [1, 1.015], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;

  return (
    <div
      style={{
        opacity,
        scale,
        minWidth: labelLike ? 210 : 360,
        maxWidth: codeLike ? 760 : 640,
        padding: labelLike ? "16px 22px" : "24px 28px",
        borderRadius: labelLike ? 999 : 24,
        border: focused ? `2px solid ${COLORS.accent}` : `1px solid ${COLORS.border}`,
        background: focused ? COLORS.accentSoft : labelLike ? COLORS.panelSoft : COLORS.panel,
        boxShadow: focused ? "0 0 0 7px rgba(110, 231, 242, 0.08)" : "none",
        fontFamily: codeLike ? "JetBrains Mono, monospace" : "Manrope, sans-serif",
        fontSize: codeLike ? 38 : 30,
        lineHeight: 1.35,
        color:
          element.kind === "output"
            ? COLORS.output
            : element.kind === "code"
              ? COLORS.code
              : element.kind === "label" && element.content.toLowerCase().includes("wyjąt")
                ? COLORS.warning
                : COLORS.text,
        whiteSpace: codeLike ? "pre-wrap" : "normal",
        overflowWrap: "anywhere",
      }}
    >
      {element.kind === "output" ? `› ${element.content}` : element.content}
    </div>
  );
};

const GenericScene: React.FC<{
  scene: ScenePlanScene;
  props: PreviewProps;
  frame: number;
  activeBeat: PreviewTimingBeat | undefined;
}> = ({scene, props, frame, activeBeat}) => {
  const anyFocus = Boolean(activeBeat?.focus_target_id);
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "30px 90px 70px",
      }}
    >
      <div
        style={{
          width: "100%",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
        }}
      >
        {scene.visible_elements.map((element) => {
          const revealFrame = firstRevealFrame(element.element_id, scene.scene_id, props.timing.beats);
          return (
            <ElementCard
              key={element.element_id}
              element={element}
              frame={frame}
              revealFrame={revealFrame}
              focused={activeBeat?.focus_target_id === element.element_id}
              anyFocus={anyFocus}
            />
          );
        })}
      </div>
    </div>
  );
};

const activeStateElement = (
  scene: ScenePlanScene,
  props: PreviewProps,
  frame: number,
): SceneElement | undefined => {
  const stateIds = ["v2-product-state", "v2-total-state", "v2-rounded-state"];
  let current: SceneElement | undefined;
  for (const id of stateIds) {
    const element = scene.visible_elements.find((item) => item.element_id === id);
    if (!element) continue;
    const reveal = firstRevealFrame(id, scene.scene_id, props.timing.beats);
    if (reveal !== null && frame >= reveal) {
      current = element;
    }
  }
  return current;
};

const UnderscoreStateScene: React.FC<{
  scene: ScenePlanScene;
  props: PreviewProps;
  frame: number;
  activeBeat: PreviewTimingBeat | undefined;
}> = ({scene, props, frame, activeBeat}) => {
  const state = activeStateElement(scene, props, frame);
  const stateReveal = state
    ? firstRevealFrame(state.element_id, scene.scene_id, props.timing.beats)
    : null;
  const excluded = new Set([
    "v2-underscore",
    "v2-product-state",
    "v2-total-state",
    "v2-rounded-state",
  ]);
  const sessionElements = scene.visible_elements.filter((element) => !excluded.has(element.element_id));

  return (
    <div
      style={{
        flex: 1,
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.65fr) minmax(340px, 0.75fr)",
        gap: 54,
        alignItems: "center",
        padding: "28px 90px 72px",
      }}
    >
      <div style={{display: "flex", flexDirection: "column", gap: 18}}>
        {sessionElements.map((element) => (
          <ElementCard
            key={element.element_id}
            element={element}
            frame={frame}
            revealFrame={firstRevealFrame(element.element_id, scene.scene_id, props.timing.beats)}
            focused={activeBeat?.focus_target_id === element.element_id}
            anyFocus={Boolean(activeBeat?.focus_target_id)}
          />
        ))}
      </div>
      <div
        style={{
          minHeight: 260,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 34,
          borderRadius: 30,
          border: `1px solid ${COLORS.border}`,
          background: COLORS.panel,
          padding: 34,
        }}
      >
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 86,
            color: COLORS.accent,
          }}
        >
          _
        </div>
        <div
          style={{
            minWidth: 220,
            minHeight: 104,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 22,
            border: `1px solid ${COLORS.border}`,
            background: COLORS.panelSoft,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 48,
            color: COLORS.output,
            opacity: state
              ? interpolate(frame, [stateReveal ?? frame, (stateReveal ?? frame) + 8], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })
              : 0,
          }}
        >
          {state?.content ?? ""}
        </div>
      </div>
    </div>
  );
};

const PreviewFrame: React.FC<PreviewProps> = (props) => {
  const frame = useCurrentFrame();
  const timingScene = findActiveScene(props, frame);
  const scene = props.scene_plan.scenes.find((row) => row.scene_id === timingScene?.scene_id);
  const activeBeat = findActiveBeat(props, frame);

  if (!scene) {
    return <AbsoluteFill style={{background: COLORS.background}} />;
  }

  const index = props.scene_plan.scenes.findIndex((row) => row.scene_id === scene.scene_id) + 1;
  return (
    <AbsoluteFill
      style={{
        background: COLORS.background,
        color: COLORS.text,
        fontFamily: "Manrope, sans-serif",
      }}
    >
      <div
        style={{
          height: 132,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 90px",
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <div>
          <div style={{fontSize: 20, letterSpacing: 2.2, color: COLORS.muted, textTransform: "uppercase"}}>
            Silent preview · scena {index}/{props.scene_plan.scenes.length}
          </div>
          <div style={{fontSize: 40, fontWeight: 700, marginTop: 7}}>{scene.title}</div>
        </div>
        <div
          style={{
            padding: "10px 16px",
            borderRadius: 999,
            border: `1px solid ${COLORS.border}`,
            color: COLORS.muted,
            fontSize: 20,
          }}
        >
          {scene.scene_type}
        </div>
      </div>

      {scene.calibration_variant_id === "v2" ? (
        <UnderscoreStateScene scene={scene} props={props} frame={frame} activeBeat={activeBeat} />
      ) : (
        <GenericScene scene={scene} props={props} frame={frame} activeBeat={activeBeat} />
      )}

      <div
        style={{
          position: "absolute",
          bottom: 24,
          right: 40,
          fontSize: 17,
          color: COLORS.muted,
          letterSpacing: 0.6,
        }}
      >
        timing: estimate · audio: OFF
      </div>
    </AbsoluteFill>
  );
};

const currentNarration = (
  fragments: NarrationFragment[],
  props: PreviewProps,
  frame: number,
) => {
  const timing = props.timing.fragments.find(
    (fragment) => frame >= fragment.start_frame && frame < fragment.end_frame,
  );
  return fragments.find((fragment) => fragment.fragment_id === timing?.fragment_id);
};

export const WebinarSilentPreview: React.FC<PreviewProps> = (props) => {
  return <PreviewFrame {...props} />;
};

export const WebinarSilentReview: React.FC<PreviewProps> = (props) => {
  const frame = useCurrentFrame();
  const narration = currentNarration(props.narration, props, frame);
  const beat = findActiveBeat(props, frame);
  const scene = findActiveScene(props, frame);
  return (
    <AbsoluteFill style={{background: "#070a12", fontFamily: "Manrope, sans-serif"}}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: props.width,
          height: props.height,
          overflow: "hidden",
        }}
      >
        <PreviewFrame {...props} />
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: props.height,
          width: props.width,
          height: props.review_strip_height,
          boxSizing: "border-box",
          padding: "18px 44px",
          display: "grid",
          gridTemplateColumns: "220px minmax(0, 1fr) 520px",
          alignItems: "center",
          gap: 28,
          borderTop: `1px solid ${COLORS.border}`,
          background: "#070a12",
          color: COLORS.text,
        }}
      >
        <div style={{color: COLORS.accent, fontSize: 18, fontWeight: 700, letterSpacing: 1.4}}>
          WORKING NARRATION
          <div style={{color: COLORS.muted, fontWeight: 400, marginTop: 5}}>{scene?.scene_id ?? "—"} · {beat?.beat_id ?? "—"}</div>
        </div>
        <div style={{fontSize: 22, lineHeight: 1.35}}>{narration?.text ?? ""}</div>
        <div style={{fontSize: 17, lineHeight: 1.35, color: COLORS.muted}}>{beat ? props.scene_plan.scenes.flatMap((row) => row.beats).find((row) => row.beat_id === beat.beat_id)?.action ?? "" : ""}</div>
      </div>
    </AbsoluteFill>
  );
};
