# Voice Guide: TTS Setup & Audio Cloning

## Architecture Overview

A voice in the pipeline is defined by: **TTS Engine + Reference Audio Sample (10–15 seconds)**.
The platform supports local generation (optimized for GPUs with $\ge 8$ GB VRAM) as well as external cloud TTS providers:

| Engine | Languages | License | Best For |
|---|---|---|---|
| **Chatterbox** (default local) | 23 languages (en, de, tr, pl, ru, etc.) | MIT | High quality cross-lingual voice cloning |
| **XTTS v2** | 17 languages | CPML | Multilingual synthesis |
| **Silero TTS** | Fast local CPU/GPU fallback | MIT | Rapid draft previews & testing |
| **Fish Audio / ElevenLabs** | Universal Cloud BYOK | Commercial | Premium broadcast quality |
| **VoiceStudio** (local app) | 646 languages | AGPL-3.0 (external app) | Cloning & voice design in a dedicated GUI |

The target language of an episode is set in the manifest (`language: en`). The orchestrator automatically routes to the appropriate engine mapped in your channel profile (`tts.language_map`).

### VoiceStudio (local companion app)

[VoiceStudio](https://github.com/debpalash/VoiceStudio) is a separate open-source
voice studio you run on your own machine (AGPL-3.0 — the pipeline integrates via
its documented HTTP API only, no code is linked). Setup:

1. Install and start VoiceStudio (backend on `127.0.0.1:3900`).
2. Generate an API key in its settings → put it in your `.env`:
   `VOICESTUDIO_API_KEY=…`.
3. Clone/design voices inside the VoiceStudio app itself; reference them by
   voice/profile id.
4. Pick the `voice_studio` provider in the episode form (or set
   `defaults.tts: voice_studio` in providers.yaml). Only clone voices you
   have the rights to.

---

## Step 1. Reference Audio Sample (Key to Quality)

Synthesis quality is 80% determined by the **reference audio sample** (10–15 seconds of clean speech):
- High-fidelity recording without background noise or music;
- Single speaker, steady and clear narration pace;
- 22,050+ Hz WAV or MP3;
- **Verbatim reference transcript** provided to the engine.

### Setting Up Your Reference Voice

Place your audio file into `models/` and specify it in `config/providers.yaml`:

```yaml
providers:
  chatterbox:
    type: tts
    adapter: chatterbox
    ref_audio: models/my_voice.wav
    ref_text: "Exact verbatim transcript of what was spoken in the audio recording."
```

Chatterbox extracts speaker timbre embeddings from this sample and can narrate any generated script using this exact tone across supported languages.

---

## Step 2. Expressiveness & Tone Tuning

Fine-tune synthesis parameters in `config/providers.yaml`:
- `exaggeration: 0.4` — Expressiveness level (`0.2` = flat, soothing, documentary; `0.8` = dynamic, energetic);
- `cfg_weight: 0.7` — Classifier-free guidance scale against the reference voice (lower values allow more spontaneous intonation);
- `speed: 1.0` — Playback and articulation tempo.

---

## Step 3. Per-Episode Voice Overrides

To use a specific voice or engine for an individual run, specify it directly in your `episode.manifest.yaml`:

```yaml
overrides:
  providers:
    tts:
      provider: chatterbox
      ref_audio: models/tech_announcer.wav
      ref_text: "Welcome to today's in-depth technology review and architectural analysis."
```
