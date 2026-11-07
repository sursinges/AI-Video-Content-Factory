# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | **Deutsch** | [Français](README.fr.md) | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** ist ein offenes modulares System für automatisierte End-to-End-Videoproduktion. Aus Themen, Ideen oder fertigen Skripten entstehen komplett geschnittene, gesprochene Videos mit Synchronisation, animierten Szenen, Ambient-Mix, Untertiteln und Publishing-Metadaten.

Das System ist **universell**: vertikale **Shorts (9:16)**, **Erklärvideos (16:9)**, **Tech-Reviews**, **Bildungs-Dokumentationen** und **atmosphärische Narrativen**.

---

## 1. Das Problem

Erzählvideos bedeuten üblicherweise Werkzeug-Hüpfen: Prompts und Szenen-Timing in LLMs; Voiceover exportieren und manuell ausrichten; passende Szenenbilder generieren; im Editor schneiden (Ken Burns, Blenden, Lautheit); Untertitel und YouTube-Metadaten formatieren. Scheitert ein Schritt, beginnt Stundenarbeit von vorn. **AI Video Content Factory** automatisiert die ganze Kette zu einem deterministischen, reproduzierbaren Conveyor: Bei Abbruch oder Szenenkorrektur wird ab dem letzten fertigen Schritt fortgesetzt — ohne Token-Verschwendung oder Re-Rendering.

---

## 2. Workflow

1. **Eingabe:** Thema, Zieldauer, Sprache, Format (oder eigenes Skript).
2. **M1 Skript:** Struktur mit Drama-Kritik, Pacing-Checks, Fact-check.
3. **M2 Audio:** TTS mit Emotions-Tags, Loudnorm, Wort-Timestamps via Whisper.
4. **M3 Visual:** deterministische Szenengrenzen (an Sprachpausen), Welt-Restriktionen, Bildgenerierung.
5. **M4 Montage:** Kamerafahrten pro Szene, Crossfades, Ambient-Mastering (−14 LUFS), Untertitel-Burn-in.
6. **M5 Metadaten:** Titel, Beschreibungen, SEO-Tags, Kapitel-Timecodes, Thumbnail.
7. **M6 Publish:** YouTube Data API v3 (oder Ordner-Export).

---

## 3. Kernfunktionen

- **Local-first & offline:** Mock-Modus komplett offline oder lokale Modelle (Silero, Stable Diffusion) ohne externe Kosten.
- **BYOK:** jeder OpenAI-kompatible LLM-Endpoint (OpenRouter, Groq…), kommerzielles TTS (Smallest.ai, ElevenLabs), Videomodelle via `.env`.
- **Checkpoints & Resume:** validierte JSON-Contracts in SQLite (`state.db`); `pipeline resume <run_id>`.
- **Cache & Budget:** gecachte Calls per Hash; `budget_limit_usd` stoppt vor teuren Überraschungen.
- **Smartes Pacing:** Schnitte nie mitten im Wort — Snap zu Sprachpausen.
- **Zwei Interfaces:** CLI (`pipeline`) und Web Studio (`pipeline ui`) mit interaktivem Storyboard und Szenen-Vorschau-Player.

---

## 4. Formate

| Format | Ratio | Auflösung | Tempo | Typischer Einsatz |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 s | Shorts/TikTok/Reels mit Burn-in-Untertiteln |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 s | Tech- und Business-Erklärungen |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 s | Hardware-/Software-Reviews |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 s | Wissenschaft, Natur, Biografien |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 s | Kommentar, Monologe |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 s | Ruhige atmosphärische Stories |

---

## 5. Fertig vs. experimentell

**Operativ:** Conveyor M1–M5 mit echtem FFmpeg-Mastering; deterministischer Dry-Run; SQLite-State-Machine; CLI; UI in 10 Sprachen; prozeduraler Ambient + CC0-Musik (Openverse, Jamendo); Wort-Untertitel (`.srt` + Burn-in); Export in eigene Ordner; Image→Video pro Szene (Kling via fal_video; live mit `FAL_KEY`); Szenen-Vorschau-Player im Storyboard.

**Experimentell:** lokales Stable Diffusion (FP16, NVIDIA ≥ 8 GB VRAM); lokales Voice-Cloning (F5-TTS/Chatterbox, PyTorch CUDA); YouTube OAuth (M6, `client_secret.json`).

---

## 6. Editionen: Desktop & Web (Cloud)

Eine Codebasis, zwei Editionen (Details: [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)):

| | **Desktop** (Community) | **Web** (Cloud) |
|---|---|---|
| Nutzer | Ein-Eigentümer, ohne Login | Multi-Tenant mit Login |
| Daten | globaler Workspace | Tenant-Daten + Tenant-BYOK |
| Abrechnung | — | Credits pro Run, Auto-Erstattung |
| Queue/Quotas | — | Run-Queue, Disk-Quotas |
| GPU-Modelle | first-class (`pip install pipeline[desktop]`) | optional |
| Install | `pip install pipeline[desktop]` → `pipeline ui` | Basis-Dependencies + `edition: web`, `hosted_mode: true` |

Erkennung über `PIPELINE_EDITION` → `ui_settings.yaml` → Standard **desktop**; `pipeline doctor` zeigt sie.

---

## 7. Systemanforderungen

**Minimum (Cloud/API):** Windows 10/11, Ubuntu 22.04+ oder macOS; Python 3.11+; FFmpeg im PATH; 8 GB RAM; 5 GB SSD.
**Empfohlen (lokal):** RTX 3060+ (8+ GB VRAM, CUDA 12.1+); 16 GB RAM; 30 GB SSD.

---

## 8. Installation

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # falls fehlt: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. Erster Start

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # öffnet http://localhost:8765
```

---

## 10. Konfiguration & BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

Keys in `pipeline/.env` (außerhalb von Git): `OPENROUTER_API_KEY`, optional `SMALLEST_AI_API_KEY`, `JAMENDO_CLIENT_ID`, `FREESOUND_TOKEN`.

Defaults in [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml): `llm: openrouter`, `tts: smallest_ai` (oder silero/chatterbox/voice_studio), `image: local_sd`, `music: ambient_synth`, `publish: mock_publish`.

---

## 11. Artefakte & Resume

Alles liegt unter `pipeline/runs/<run_id>/`: `script/script.json`, `audio/episode.wav` + `speechplan.json`, `subtitles/subtitles.srt` (+ Wort-JSON), `visual/world.json` + `scenes.json` + `assets/`, `video/episode.mp4` + `timecodes.txt` + `effects_report.json`, `metadata/metadata.json` + `thumbnail.png`.

Bei Fehlern: `python -m core.cli resume ep-0001` — fertige Schritte werden übersprungen.

---

## 12. Troubleshooting

| Symptom | Ursache | Lösung |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg nicht im PATH | FFmpeg installieren, Terminal neu starten. |
| `CUDA out of memory` | SD passt nicht in VRAM | Auflösung senken (`image_size: [768, 432]`) oder externen Image-Provider nutzen. |
| `HTTP 429` | Provider-Quota | Router retryt oder fällt auf `fallbacks:` zurück. |
| `NameError` in Tests | pipeline nicht im Python-Path | `pytest` aus dem Repo-Root starten. |

---

## 13. Status & Roadmap

- [x] Kern-Conveyor M1–M4; Metadaten (S5); Web Studio; Doctor; universelle Formate.
- [x] Image→Video pro Szene (Kling/fal_video; live mit `FAL_KEY`).
- [x] Cloud-Packaging: Dockerfile + systemd/Caddy-Installer.
- [ ] Batch-Serienproduktion.

---

## 14. Dokumentation

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. Lizenz

**MIT** (siehe [LICENSE](LICENSE)). Komponenten, die Fremdmodelle einbinden (Silero, Coqui XTTS, Stable Diffusion), folgen den jeweiligen Upstream-Lizenzen.
