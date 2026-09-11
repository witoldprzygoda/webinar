import React from "react";
import {Composition} from "remotion";
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
    </>
  );
};
