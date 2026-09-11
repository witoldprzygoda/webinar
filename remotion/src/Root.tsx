import React from "react";
import {Composition} from "remotion";
import {VisualCalibration, type VisualCalibrationProps} from "./VisualCalibration";
import {WebinarSilentPreview, WebinarSilentReview} from "./WebinarPreview";
import type {PreviewProps} from "./types";

const emptyProps: PreviewProps = {
  schema_version: 1,
  lesson_id: "empty",
  lesson_title: "M3c preview requires --props",
  artifact_sha256: "",
  gate_a_approval_sha256: "",
  m3a_selection_sha256: "",
  visual_fact_catalog_sha256: "",
  scene_plan_sha256: "",
  m3b_preview_acceptance_sha256: "",
  fps: 30,
  width: 1920,
  height: 1080,
  review_strip_height: 150,
  audio_enabled: false,
  render_requested: false,
  narration: [],
  scene_plan: {
    schema_version: 2,
    artifact_sha256: "",
    gate_a_approval_sha256: "",
    m3a_selection_sha256: "",
    visual_fact_catalog_sha256: "",
    role: "scene_designer",
    lesson_title: "M3c preview requires --props",
    selected_calibration_variant_id: "",
    scenes: [],
    component_requests: [],
    design_note: "",
  },
  timing: {
    schema_version: 1,
    timing_kind: "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW",
    replace_with_audio_alignment: true,
    fps: 30,
    words_per_minute: 138,
    total_frames: 300,
    scenes: [],
    fragments: [],
    beats: [],
    preview_timing_sha256: "",
  },
  preview_props_sha256: "",
};

const emptyCalibrationProps: VisualCalibrationProps = {
  schema_version: 1,
  lesson_id: "empty",
  scene_id: "s00",
  scene_index: 0,
  variant_id: "calibration-empty",
  theme: "dark",
  layout: "editorial_stack",
  motion: "soft_rise",
  fps: 30,
  width: 1920,
  height: 1080,
  duration_frames: 300,
  content_start_frame: 18,
  content_end_frame: 282,
  narration_fragment_ids: [],
  narration_text: "",
  screen_copy: {
    eyebrow: "M3c0",
    title: "Visual calibration requires --props",
    items: [],
    footer: "silent preview",
  },
  original_scene: {
    scene_id: "s00",
    title: "Visual calibration requires --props",
    scene_type: "OPEN",
    narration_fragment_ids: [],
    pedagogical_goal: "",
    visual_strategy: "",
    calibration_variant_id: "",
    requires_new_component: false,
    component_request_id: "",
    visible_elements: [],
    beats: [],
    risks: [],
  },
};

const metadata = ({props}: {props: PreviewProps}) => ({
  durationInFrames: Math.max(1, props.timing?.total_frames ?? 300),
  fps: props.fps ?? 30,
  width: props.width ?? 1920,
  height: props.height ?? 1080,
});

const reviewMetadata = ({props}: {props: PreviewProps}) => ({
  durationInFrames: Math.max(1, props.timing?.total_frames ?? 300),
  fps: props.fps ?? 30,
  width: props.width ?? 1920,
  height: (props.height ?? 1080) + (props.review_strip_height ?? 150),
});

const calibrationMetadata = ({props}: {props: VisualCalibrationProps}) => ({
  durationInFrames: Math.max(1, props.duration_frames ?? 300),
  fps: props.fps ?? 30,
  width: props.width ?? 1920,
  height: props.height ?? 1080,
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="WebinarSilentPreview"
        component={WebinarSilentPreview}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={emptyProps}
        calculateMetadata={metadata}
      />
      <Composition
        id="WebinarSilentReview"
        component={WebinarSilentReview}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1230}
        defaultProps={emptyProps}
        calculateMetadata={reviewMetadata}
      />
      <Composition
        id="VisualCalibration"
        component={VisualCalibration}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={emptyCalibrationProps}
        calculateMetadata={calibrationMetadata}
      />
    </>
  );
};
