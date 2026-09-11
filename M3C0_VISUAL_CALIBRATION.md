# M3c0 visual-language calibration

M3c0 is a short human calibration stage before building another full silent preview.
It exists because a semantically correct M3b scene plan is not enough to choose a
visual language for Remotion.

## Purpose

- keep the Gate A narration immutable;
- separate concise screen copy from spoken narration;
- compare genuinely different layouts, themes and motion patterns on only a few scenes;
- use terminal/REPL semantics for code scenes instead of generic cards;
- produce finite MP4 clips for review, not a long-running Studio server;
- produce a matching `.srt` sidecar for every calibration clip.

The current calibration set uses the first three scenes of `python-console-calculator`:

- `s01`: eight concept-slide variants;
- `s02`: six REPL variants;
- `s03`: six REPL variants.

That is 20 short calibration clips in total. Intro variants include dark, light and
paper treatments, vertical editorial layouts, a left rail, semantic flow, spotlight
and kinetic alignment. REPL variants include a recognizable terminal window,
minimal terminal, split explanation, paper/code-sheet and command-focus treatments.

## Screen copy vs narration

`config/m3c0_visual_calibration.json` contains concise screen copy. It is presentation
copy only and does not replace or modify the approved narration. The `.srt` text is
always taken from the exact narration stored in the source M3c `preview-props.json`.

## Generate and render

From the repository root:

```bash
./.venv/Scripts/python.exe flows/m3c0_visual_calibration.py \
  runs/m3c-preview/<M3C_RUN_ID> \
  --scene-count 3 \
  --render
```

The command creates:

```text
runs/m3c0-calibration/<RUN_ID>/
  manifest.json
  props/
    <scene>-<variant>.json
  clips/
    <scene>-<variant>.mp4
    <scene>-<variant>.srt
```

The render is finite: the command exits after all requested MP4 clips are rendered.
No ElevenLabs/audio call is made.

## Human review

The reviewer should compare visual hierarchy, use of screen space, readability,
semantic fidelity of the visual metaphor, motion restraint, and whether reveals
help follow the spoken argument. Selection here calibrates the visual language; it
is not Gate B and does not approve the full lesson.
