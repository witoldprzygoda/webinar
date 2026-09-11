import "@fontsource/manrope/400.css";
import "@fontsource/manrope/700.css";
import "@fontsource/jetbrains-mono/400.css";

import React from "react";
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import type {ScenePlanScene} from "./types";

export type CalibrationScreenCopy = {
  eyebrow: string;
  title: string;
  items: string[];
  footer: string;
};

export type VisualCalibrationProps = {
  schema_version: 1;
  lesson_id: string;
  scene_id: string;
  scene_index: number;
  variant_id: string;
  theme: "dark" | "light" | "paper";
  layout: string;
  motion: string;
  fps: number;
  width: number;
  height: number;
  duration_frames: number;
  content_start_frame: number;
  content_end_frame: number;
  narration_fragment_ids: string[];
  narration_text: string;
  screen_copy: CalibrationScreenCopy;
  original_scene: ScenePlanScene;
};

type Palette = {
  bg: string;
  bg2: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
  panel: string;
  border: string;
  code: string;
  output: string;
};

const paletteFor = (theme: VisualCalibrationProps["theme"]): Palette => {
  if (theme === "light") {
    return {
      bg: "#f5f7fb",
      bg2: "#e9eef7",
      text: "#111827",
      muted: "#607089",
      accent: "#0f6f8f",
      accent2: "#0d9488",
      panel: "#ffffff",
      border: "rgba(15, 23, 42, 0.14)",
      code: "#172033",
      output: "#087f5b",
    };
  }
  if (theme === "paper") {
    return {
      bg: "#f4efe6",
      bg2: "#ebe3d6",
      text: "#22201c",
      muted: "#746f66",
      accent: "#8f3e2f",
      accent2: "#406c70",
      panel: "#fbf8f2",
      border: "rgba(57, 48, 39, 0.18)",
      code: "#292620",
      output: "#2f6f55",
    };
  }
  return {
    bg: "#090d16",
    bg2: "#111827",
    text: "#f5f7fb",
    muted: "#8e9ab0",
    accent: "#67d4e8",
    accent2: "#8fe3b8",
    panel: "#101827",
    border: "rgba(255,255,255,0.12)",
    code: "#edf4ff",
    output: "#98e6b8",
  };
};

const appear = (frame: number, at: number, span = 14) =>
  interpolate(frame, [at, at + span], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const rise = (frame: number, at: number, distance = 22) =>
  interpolate(frame, [at, at + 18], [distance, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const progress = (frame: number, at: number, span = 24) =>
  interpolate(frame, [at, at + span], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const Chrome: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => (
  <>
    <div
      style={{
        position: "absolute",
        top: 54,
        right: 66,
        fontFamily: "Manrope, sans-serif",
        fontSize: 18,
        letterSpacing: 1.2,
        color: palette.muted,
        textTransform: "uppercase",
      }}
    >
      M3c0 · {props.variant_id}
    </div>
    <div
      style={{
        position: "absolute",
        left: 68,
        bottom: 48,
        fontFamily: "Manrope, sans-serif",
        fontSize: 18,
        letterSpacing: 0.8,
        color: palette.muted,
      }}
    >
      {props.screen_copy.footer}
    </div>
  </>
);

const EditorialStack: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 150, top: 150, width: 1500}}>
        <div
          style={{
            opacity: appear(frame, start),
            translate: `0 ${rise(frame, start, 14)}px`,
            fontFamily: "Manrope, sans-serif",
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: 2.4,
            color: palette.accent,
            textTransform: "uppercase",
          }}
        >
          {props.screen_copy.eyebrow}
        </div>
        <div
          style={{
            opacity: appear(frame, start + 5),
            translate: `0 ${rise(frame, start + 5, 24)}px`,
            marginTop: 26,
            maxWidth: 1220,
            fontFamily: "Manrope, sans-serif",
            fontSize: 92,
            lineHeight: 1.02,
            fontWeight: 700,
            letterSpacing: -3.5,
            color: palette.text,
          }}
        >
          {props.screen_copy.title}
        </div>
      </div>
      <div style={{position: "absolute", left: 154, top: 515, width: 1420}}>
        {props.screen_copy.items.map((item, index) => {
          const at = start + 22 + index * 20;
          return (
            <div
              key={item}
              style={{
                height: 118,
                display: "grid",
                gridTemplateColumns: "72px minmax(0,1fr)",
                alignItems: "center",
                borderTop: `1px solid ${palette.border}`,
                opacity: appear(frame, at),
                translate: `${rise(frame, at, 16)}px 0`,
              }}
            >
              <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: 20, color: palette.accent}}>
                0{index + 1}
              </div>
              <div style={{fontFamily: "Manrope, sans-serif", fontSize: 44, color: palette.text}}>{item}</div>
            </div>
          );
        })}
      </div>
    </>
  );
};

const LeftRail: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  const lineScale = progress(frame, start + 3, 30);
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 156,
          top: 136,
          width: 4,
          height: 790,
          background: palette.accent,
          scale: `1 ${lineScale}`,
          transformOrigin: "top",
        }}
      />
      <div style={{position: "absolute", left: 215, top: 146, width: 1370}}>
        <div style={{opacity: appear(frame, start), fontSize: 23, color: palette.accent, letterSpacing: 2.2, textTransform: "uppercase", fontWeight: 700}}>
          {props.screen_copy.eyebrow}
        </div>
        <div style={{opacity: appear(frame, start + 6), translate: `0 ${rise(frame, start + 6, 20)}px`, marginTop: 34, fontSize: 86, lineHeight: 1.05, fontWeight: 700, letterSpacing: -3, color: palette.text}}>
          {props.screen_copy.title}
        </div>
        <div style={{marginTop: 105, display: "flex", flexDirection: "column", gap: 38}}>
          {props.screen_copy.items.map((item, index) => {
            const at = start + 25 + index * 21;
            return (
              <div key={item} style={{display: "grid", gridTemplateColumns: "80px 1fr", alignItems: "baseline", opacity: appear(frame, at), translate: `${rise(frame, at, 20)}px 0`}}>
                <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: 25, color: palette.muted}}>{index + 1}.</div>
                <div style={{fontSize: 48, color: palette.text}}>{item}</div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

const SemanticFlow: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 150, top: 140, width: 1540}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, letterSpacing: 2.4, textTransform: "uppercase", color: palette.accent, fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 22, fontSize: 76, fontWeight: 700, letterSpacing: -2.8, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 205, top: 510, width: 1510, display: "grid", gridTemplateColumns: "1fr 150px 1fr 150px 1fr", alignItems: "center"}}>
        {props.screen_copy.items.map((item, index) => {
          const at = start + 25 + index * 18;
          return (
            <React.Fragment key={item}>
              <div style={{opacity: appear(frame, at), translate: `0 ${rise(frame, at, 20)}px`, minHeight: 210, display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "36px 8px 28px", borderTop: `3px solid ${index === 1 ? palette.accent2 : palette.accent}`, borderBottom: `1px solid ${palette.border}`}}>
                <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: 20, color: palette.muted}}>0{index + 1}</div>
                <div style={{fontSize: 38, lineHeight: 1.2, color: palette.text}}>{item}</div>
              </div>
              {index < props.screen_copy.items.length - 1 ? (
                <div style={{opacity: progress(frame, at + 8, 18), height: 2, background: palette.border, position: "relative", margin: "0 26px"}}>
                  <div style={{position: "absolute", right: -1, top: -5, width: 10, height: 10, borderTop: `2px solid ${palette.accent}`, borderRight: `2px solid ${palette.accent}`, rotate: "45deg"}} />
                </div>
              ) : null}
            </React.Fragment>
          );
        })}
      </div>
    </>
  );
};

const Spotlight: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  const active = Math.min(props.screen_copy.items.length - 1, Math.max(0, Math.floor((frame - start - 24) / 24)));
  return (
    <>
      <div style={{position: "absolute", left: 135, top: 150, width: 690}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, color: palette.accent, letterSpacing: 2.2, textTransform: "uppercase", fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 30, fontSize: 92, fontWeight: 700, lineHeight: 1.02, letterSpacing: -3.4, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 915, top: 260, width: 760}}>
        {props.screen_copy.items.map((item, index) => {
          const at = start + 24 + index * 24;
          const selected = index === active;
          return (
            <div key={item} style={{height: 150, display: "flex", alignItems: "center", borderBottom: `1px solid ${palette.border}`, opacity: appear(frame, at) * (selected ? 1 : 0.38), translate: `${selected ? 0 : 28}px 0`}}>
              <div style={{width: 62, fontFamily: "JetBrains Mono, monospace", color: selected ? palette.accent : palette.muted, fontSize: 21}}>0{index + 1}</div>
              <div style={{fontSize: selected ? 48 : 40, fontWeight: selected ? 700 : 400, color: palette.text}}>{item}</div>
            </div>
          );
        })}
      </div>
    </>
  );
};

const KineticColumn: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 145, top: 128, width: 1580}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, fontWeight: 700, color: palette.accent, textTransform: "uppercase", letterSpacing: 2.4}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 20, fontSize: 82, fontWeight: 700, letterSpacing: -3, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 150, top: 490, width: 1520}}>
        {props.screen_copy.items.map((item, index) => {
          const at = start + 20 + index * 20;
          const x = interpolate(frame, [at, at + 20], [index % 2 === 0 ? -80 : 80, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)});
          return (
            <div key={item} style={{height: 132, display: "grid", gridTemplateColumns: "110px 1fr", alignItems: "center", opacity: appear(frame, at), translate: `${x}px 0`, borderTop: `1px solid ${palette.border}`}}>
              <div style={{fontSize: 56, fontWeight: 700, color: index === 1 ? palette.accent2 : palette.accent}}>0{index + 1}</div>
              <div style={{fontSize: 47, color: palette.text}}>{item}</div>
            </div>
          );
        })}
      </div>
    </>
  );
};

type TerminalRow = {code: string; output?: string};

const terminalRows = (scene: ScenePlanScene): TerminalRow[] => {
  const rows: TerminalRow[] = [];
  for (const element of scene.visible_elements) {
    if (element.kind === "code") {
      rows.push({code: element.content});
      continue;
    }
    if (element.kind === "output" && rows.length > 0 && rows[rows.length - 1].output === undefined) {
      rows[rows.length - 1].output = element.content;
    }
  }
  return rows.slice(0, 4);
};

const TerminalLines: React.FC<{
  props: VisualCalibrationProps;
  palette: Palette;
  compact?: boolean;
  activeOnly?: boolean;
}> = ({props, palette, compact = false, activeOnly = false}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame + 12;
  const rows = terminalRows(props.original_scene);
  if (rows.length === 0) {
    return <div style={{fontSize: 34, color: palette.muted}}>Brak faktów kodowych do prezentacji.</div>;
  }
  const step = Math.max(22, Math.floor((props.content_end_frame - start - 10) / Math.max(1, rows.length)));
  const activeIndex = Math.min(rows.length - 1, Math.max(0, Math.floor((frame - start) / step)));
  return (
    <div style={{display: "flex", flexDirection: "column", gap: compact ? 22 : 32}}>
      {rows.map((row, index) => {
        const at = start + index * step;
        const rowOpacity = appear(frame, at, 10) * (activeOnly && index !== activeIndex ? 0.24 : 1);
        return (
          <div key={`${row.code}-${index}`} style={{opacity: rowOpacity, translate: `0 ${rise(frame, at, 12)}px`}}>
            <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: compact ? 34 : 42, lineHeight: 1.35, color: palette.code}}>
              <span style={{color: palette.accent, marginRight: 18}}>&gt;&gt;&gt;</span>{row.code}
            </div>
            {row.output !== undefined ? (
              <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: compact ? 32 : 40, lineHeight: 1.35, color: palette.output, paddingLeft: compact ? 76 : 88, marginTop: 8}}>
                {row.output}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

const TerminalWindow: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 135, top: 115, width: 1550}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, letterSpacing: 2.2, textTransform: "uppercase", fontWeight: 700, color: palette.accent}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 4), marginTop: 18, fontSize: 68, fontWeight: 700, letterSpacing: -2.4, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 190, top: 330, width: 1540, height: 600, border: `1px solid ${palette.border}`, borderRadius: 18, background: palette.panel, boxShadow: props.theme === "dark" ? "0 28px 80px rgba(0,0,0,0.34)" : "0 24px 70px rgba(55,65,81,0.12)", overflow: "hidden", opacity: appear(frame, start + 8), translate: `0 ${rise(frame, start + 8, 18)}px`}}>
        <div style={{height: 58, display: "flex", alignItems: "center", gap: 10, padding: "0 24px", borderBottom: `1px solid ${palette.border}`}}>
          {[0, 1, 2].map((x) => <div key={x} style={{width: 11, height: 11, borderRadius: 999, background: x === 0 ? "#f0746b" : x === 1 ? "#e6ba57" : "#65c483", opacity: 0.9}} />)}
          <div style={{marginLeft: 18, fontFamily: "JetBrains Mono, monospace", fontSize: 16, color: palette.muted}}>Python 3.14 · REPL</div>
        </div>
        <div style={{padding: "54px 70px"}}><TerminalLines props={props} palette={palette} /></div>
      </div>
    </>
  );
};

const TerminalMinimal: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 150, top: 130, width: 1470}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, color: palette.accent, textTransform: "uppercase", letterSpacing: 2.2, fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 20, fontSize: 76, fontWeight: 700, letterSpacing: -2.7, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 205, top: 420, width: 1350}}><TerminalLines props={props} palette={palette} /></div>
      <div style={{position: "absolute", left: 1510, top: 424, width: 210, height: 2, background: palette.accent, scale: `${progress(frame, start + 20, 30)} 1`, transformOrigin: "left"}} />
    </>
  );
};

const TerminalSplit: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 135, top: 120, width: 1550}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, color: palette.accent, textTransform: "uppercase", letterSpacing: 2.2, fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 18, fontSize: 70, fontWeight: 700, letterSpacing: -2.5, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 135, top: 360, width: 1050, height: 585, padding: "54px 60px", boxSizing: "border-box", borderTop: `2px solid ${palette.accent}`, background: palette.panel, opacity: appear(frame, start + 10)}}>
        <TerminalLines props={props} palette={palette} compact />
      </div>
      <div style={{position: "absolute", left: 1280, top: 405, width: 470}}>
        {props.screen_copy.items.map((item, index) => {
          const at = start + 28 + index * 24;
          return <div key={item} style={{padding: "30px 0", borderBottom: `1px solid ${palette.border}`, opacity: appear(frame, at), translate: `${rise(frame, at, 20)}px 0`, fontSize: 31, lineHeight: 1.35, color: palette.text}}>{item}</div>;
        })}
      </div>
    </>
  );
};

const CodeSheet: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  return (
    <>
      <div style={{position: "absolute", left: 145, top: 115, width: 1500}}>
        <div style={{opacity: appear(frame, start), fontSize: 21, color: palette.accent, textTransform: "uppercase", letterSpacing: 2.2, fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 18, fontSize: 69, fontWeight: 700, letterSpacing: -2.4, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      <div style={{position: "absolute", left: 175, top: 335, width: 1540, height: 615, background: palette.panel, border: `1px solid ${palette.border}`, boxShadow: "0 24px 60px rgba(60,50,40,0.10)", opacity: appear(frame, start + 9)}}>
        <div style={{position: "absolute", left: 86, top: 0, bottom: 0, width: 1, background: palette.border}} />
        <div style={{padding: "66px 80px 60px 125px"}}><TerminalLines props={props} palette={palette} /></div>
      </div>
    </>
  );
};

const CommandFocus: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  const frame = useCurrentFrame();
  const start = props.content_start_frame;
  const rows = terminalRows(props.original_scene);
  const step = Math.max(30, Math.floor((props.content_end_frame - start - 12) / Math.max(1, rows.length)));
  const activeIndex = Math.min(rows.length - 1, Math.max(0, Math.floor((frame - start - 12) / step)));
  const row = rows[activeIndex];
  return (
    <>
      <div style={{position: "absolute", left: 145, top: 125, width: 1500}}>
        <div style={{opacity: appear(frame, start), fontSize: 22, color: palette.accent, textTransform: "uppercase", letterSpacing: 2.2, fontWeight: 700}}>{props.screen_copy.eyebrow}</div>
        <div style={{opacity: appear(frame, start + 5), marginTop: 18, fontSize: 68, fontWeight: 700, letterSpacing: -2.4, color: palette.text}}>{props.screen_copy.title}</div>
      </div>
      {row ? (
        <div style={{position: "absolute", left: 190, top: 430, width: 1500}}>
          <div style={{fontFamily: "JetBrains Mono, monospace", fontSize: 72, color: palette.code, letterSpacing: -1.5}}><span style={{color: palette.accent, marginRight: 28}}>&gt;&gt;&gt;</span>{row.code}</div>
          {row.output !== undefined ? <div style={{marginTop: 78, paddingLeft: 123, fontFamily: "JetBrains Mono, monospace", fontSize: 84, fontWeight: 700, color: palette.output, opacity: appear(frame, start + 20 + activeIndex * step), translate: `0 ${rise(frame, start + 20 + activeIndex * step, 26)}px`}}>{row.output}</div> : null}
          <div style={{marginTop: 60, marginLeft: 123, width: 1180, height: 1, background: palette.border}} />
        </div>
      ) : null}
    </>
  );
};

const ConceptScene: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  switch (props.layout) {
    case "left_rail": return <LeftRail props={props} palette={palette} />;
    case "semantic_flow": return <SemanticFlow props={props} palette={palette} />;
    case "spotlight": return <Spotlight props={props} palette={palette} />;
    case "kinetic_column": return <KineticColumn props={props} palette={palette} />;
    default: return <EditorialStack props={props} palette={palette} />;
  }
};

const ReplScene: React.FC<{props: VisualCalibrationProps; palette: Palette}> = ({props, palette}) => {
  switch (props.layout) {
    case "terminal_minimal": return <TerminalMinimal props={props} palette={palette} />;
    case "terminal_split": return <TerminalSplit props={props} palette={palette} />;
    case "code_sheet": return <CodeSheet props={props} palette={palette} />;
    case "command_focus": return <CommandFocus props={props} palette={palette} />;
    default: return <TerminalWindow props={props} palette={palette} />;
  }
};

export const VisualCalibration: React.FC<VisualCalibrationProps> = (props) => {
  const palette = paletteFor(props.theme);
  const hasCode = props.original_scene.visible_elements.some((element) => element.kind === "code");
  return (
    <AbsoluteFill style={{background: palette.bg, color: palette.text, fontFamily: "Manrope, sans-serif", overflow: "hidden"}}>
      <div style={{position: "absolute", inset: 0, background: `radial-gradient(circle at 78% 18%, ${palette.bg2} 0%, transparent 38%)`, opacity: props.theme === "dark" ? 0.65 : 0.5}} />
      {hasCode ? <ReplScene props={props} palette={palette} /> : <ConceptScene props={props} palette={palette} />}
      <Chrome props={props} palette={palette} />
    </AbsoluteFill>
  );
};
