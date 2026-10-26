# Media Asset Standards & Rules (ASSET RULES)

This document establishes quality guidelines for media assets generated across conveyor stages: scripts, voiceovers, images, motion effects, and metadata.

---

## 1. Scripting Stage (M1 Script)

1. **Formats & Objectives:**
   - Universal adaptation for requested format (`short_vertical`, `tech_review`, `explainer`, `educational_narrative`, `sleep_history`).
   - Tone matches profile: conversational, structured, authoritative, or atmospheric depending on format.
2. **Structure Requirements:**
   - **Hook & Introduction:** Captures audience attention in the opening 3–5 seconds; sets up premise and core question.
   - **Body Chunks:** Logical progression from cause to effect; clear insights without unnecessary filler.
   - **Resolution & Outro:** Synthesizes main takeaways and delivers payoff.
3. **Validation & Quality Control:**
   - Enforce machine validation against cliches, repetitive syntax, and AI-typical intros ("In today's fast-paced world...").
   - Strict scene boundary alignment with estimated narration durations.

---

## 2. Audio & Speech Stage (M2 Audio / TTS)

1. **Audio Engineering Standards:**
   - Sample rate: 24,000 Hz or 44,100 Hz.
   - Normalization: EBU R128 (-14 LUFS target for streaming, True Peak $\le -1.5$ dBFS).
2. **Delivery & Pacing:**
   - Controlled speech pace (`0.95x – 1.05x` for long-form; `1.05x – 1.15x` for short-form).
   - Natural inter-sentence pauses (300–600 ms).
   - Low-noise voice reference samples for zero-shot cloning.

---

## 3. Visuals & Art Direction (M3 Visual & Presets)

1. **Geometry & Aspect Ratio:**
   - Standard Horizontal: `16:9` (`1920x1080`).
   - Vertical Shorts / Reels: `9:16` (`1080x1920`).
2. **Preset Aesthetics:**
   - `dark_history_cinematic`: 35mm film grain, chiaroscuro lighting, desaturated historical tones.
   - `flat_vector_night`: Modern vector styling with dark color accents for tech explainers.
3. **Negative Prompting:**
   - Eliminate low-quality AI artifacts: `cartoon, 3d render, anime, cgi, vibrant bright neon colors, oversaturated, smooth plastic skin, digital illustration, collage, split screen, multiple frames, distorted faces, watermark, text, signature, bad anatomy`.

---

## 4. Video Assembly & Motion (M4 Assembly)

1. **Dynamic Motion (Ken Burns & FX):**
   - Purely static images are avoided: every scene includes subtle cinematic camera moves (slow zoom in, gentle pan, parallax crop).
2. **Pacing & Transitions:**
   - Smooth crossfades (0.5–1.0s) for documentary narratives.
   - Quick cuts (0.1–0.3s) for vertical short-form content.
3. **Subtitle Synchronization:**
   - Burned-in subtitles positioned within safe margins (avoiding platform UI buttons on Shorts/Reels/TikTok).
