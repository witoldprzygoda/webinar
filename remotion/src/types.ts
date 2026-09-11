export type NarrationFragment = {
  fragment_id: string;
  text: string;
};

export type SceneElement = {
  element_id: string;
  kind: "code" | "output" | "label" | "state" | "panel" | "diagram" | "pointer_target" | "other";
  source_type: "fact" | "narration_quote" | "visual_label";
  fact_id: string;
  fragment_id: string;
  content: string;
  provenance?: string;
  source_ref?: string;
};

export type SceneBeat = {
  beat_id: string;
  narration_fragment_id: string;
  anchor_text: string;
  action: string;
  focus_target_id: string;
  reveals: string[];
};

export type ScenePlanScene = {
  scene_id: string;
  title: string;
  scene_type: string;
  narration_fragment_ids: string[];
  pedagogical_goal: string;
  visual_strategy: string;
  calibration_variant_id: string;
  requires_new_component: boolean;
  component_request_id: string;
  visible_elements: SceneElement[];
  beats: SceneBeat[];
  risks: string[];
};

export type ScenePlan = {
  schema_version: number;
  artifact_sha256: string;
  gate_a_approval_sha256: string;
  m3a_selection_sha256: string;
  visual_fact_catalog_sha256: string;
  role: string;
  lesson_title: string;
  selected_calibration_variant_id: string;
  scenes: ScenePlanScene[];
  component_requests: Array<{
    component_id: string;
    purpose: string;
    used_in_scene_ids: string[];
    origin_variant_id: string;
  }>;
  design_note: string;
};

export type PreviewTimingScene = {
  scene_id: string;
  start_frame: number;
  content_start_frame: number;
  content_end_frame: number;
  end_frame: number;
  duration_frames: number;
  fragment_ids: string[];
  beat_ids: string[];
};

export type PreviewTimingFragment = {
  fragment_id: string;
  scene_id: string;
  start_frame: number;
  end_frame: number;
  duration_frames: number;
  timing_source: string;
};

export type PreviewTimingBeat = {
  beat_id: string;
  scene_id: string;
  fragment_id: string;
  start_frame: number;
  end_frame: number;
  focus_target_id: string;
  reveals: string[];
};

export type PreviewTiming = {
  schema_version: number;
  timing_kind: "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW";
  replace_with_audio_alignment: true;
  fps: number;
  words_per_minute: number;
  total_frames: number;
  scenes: PreviewTimingScene[];
  fragments: PreviewTimingFragment[];
  beats: PreviewTimingBeat[];
  preview_timing_sha256: string;
};

export type PreviewProps = {
  schema_version: number;
  lesson_id: string;
  lesson_title: string;
  artifact_sha256: string;
  gate_a_approval_sha256: string;
  m3a_selection_sha256: string;
  visual_fact_catalog_sha256: string;
  scene_plan_sha256: string;
  m3b_preview_acceptance_sha256: string;
  fps: number;
  width: number;
  height: number;
  review_strip_height: number;
  audio_enabled: false;
  render_requested: false;
  narration: NarrationFragment[];
  scene_plan: ScenePlan;
  timing: PreviewTiming;
  preview_props_sha256: string;
};
