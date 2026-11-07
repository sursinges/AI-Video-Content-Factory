# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | **Français** | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** est un système modulaire ouvert pour la production vidéo automatisée de bout en bout. Il transforme un thème, une idée ou un script existant en vidéo complète : narration synchronisée, scènes animées, mixage ambiant, sous-titres et métadonnées de publication.

Le système est **universel** : **vidéos verticales courtes (9:16)**, **vidéos explicatives (16:9)**, **tests tech**, **documentaires pédagogiques** et **narrations immersives**.

---

## 1. Le problème

Créer une vidéo narrée impose de jongler entre outils : prompts et scènes minutées dans des LLM, export de voix-off à aligner manuellement, génération d’illustrations cohérentes, montage (Ken Burns, fondus, loudness), sous-titres et métadonnées YouTube. Au moindre accroc, on refait des heures. **AI Video Content Factory** automatise toute la chaîne en un convoyeur déterministe et reproductible : en cas d’échec ou de correction, on reprend au dernier étape terminée — sans gaspiller de tokens ni re-rendre l’existant.

---

## 2. Flux de production

1. **Entrée :** thème, durée cible, langue, format (ou votre propre script).
2. **M1 Script :** structure en blocs, critique dramatique, fact-check.
3. **M2 Audio :** synthèse TTS avec tags d’émotion, normalisation, timestamps par mot via Whisper.
4. **M3 Visuel :** découpage déterministe des scènes (sur les pauses de parole), contraintes du monde, génération d’images.
5. **M4 Montage :** mouvements de caméra par scène, fondus enchaînés, mixage ambiant (−14 LUFS), sous-titres incrustés.
6. **M5 Métadonnées :** titres, descriptions, tags SEO, timecodes de chapitres, miniature.
7. **M6 Publication :** YouTube Data API v3 (ou export dossier).

---

## 3. Capacités clés

- **Local-first & hors ligne :** mode mock entièrement hors ligne ou modèles locaux (Silero, Stable Diffusion) sans frais externes.
- **BYOK :** tout endpoint LLM compatible OpenAI (OpenRouter, Groq…), TTS commercial (Smallest.ai, ElevenLabs) ou modèles vidéo via `.env`.
- **Checkpoints & reprise :** contrats JSON validés en SQLite (`state.db`) ; `pipeline resume <run_id>`.
- **Cache & budget :** appels cachés par hash ; `budget_limit_usd` stoppe avant les surprises.
- **Rythme intelligent :** jamais de coupe en plein mot — alignement sur les pauses détectées par Whisper.
- **Double interface :** CLI (`pipeline`) et Web Studio (`pipeline ui`) avec storyboard interactif et aperçu de scène.

---

## 4. Formats

| Format | Ratio | Résolution | Rythme | Usage typique |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 s | Shorts/TikTok/Reels sous-titrés |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 s | Explicatifs tech et business |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 s | Tests hardware/software |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 s | Science, nature, biographies |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 s | Commentaires, monologues |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 s | Histoires atmosphériques de fond |

---

## 5. Fonctionnel vs expérimental

**Opérationnel :** convoyeur M1–M5 avec masterisation FFmpeg réelle ; dry-run déterministe ; state machine SQLite ; CLI ; interface en 10 langues ; ambient procédural + musique CC0 (Openverse, Jamendo) ; sous-titres par mot (`.srt` + incrustation) ; export dossier personnalisé ; image→vidéo par scène (Kling via fal_video ; live avec `FAL_KEY`) ; aperçu de scène jouable dans le storyboard.

**Expérimental :** Stable Diffusion local (FP16, NVIDIA ≥ 8 Go VRAM) ; clonage vocal local (F5-TTS/Chatterbox, PyTorch CUDA) ; YouTube OAuth (M6, `client_secret.json`).

---

## 6. Éditions : Desktop & Web (Cloud)

Une base de code, deux éditions (détails : [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)) :

| | **Desktop** (Community) | **Web** (Cloud) |
|---|---|---|
| Utilisateurs | propriétaire unique, sans connexion | multi-tenant avec connexion |
| Données | workspace global | données + BYOK par tenant |
| Facturation | — | crédits par run, remboursement auto |
| File/quotas | — | file d’attente, quotas disque |
| Modèles GPU locaux | first-class (`pip install pipeline[desktop]`) | optionnel |
| Install | `pip install pipeline[desktop]` → `pipeline ui` | deps de base + `edition: web`, `hosted_mode: true` |

Détectée via `PIPELINE_EDITION` → `ui_settings.yaml` → par défaut **desktop** ; `pipeline doctor` l’indique.

---

## 7. Prérequis

**Minimum (cloud/API) :** Windows 10/11, Ubuntu 22.04+ ou macOS ; Python 3.11+ ; FFmpeg dans le PATH ; 8 Go RAM ; 5 Go disque.
**Recommandé (local) :** RTX 3060+ (8+ Go VRAM, CUDA 12.1+) ; 16 Go RAM ; 30 Go SSD.

---

## 8. Installation

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # sinon : winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. Premier lancement

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # ouvre http://localhost:8765
```

---

## 10. Configuration & BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

Clés dans `pipeline/.env` (hors git) : `OPENROUTER_API_KEY`, optionnelles `SMALLEST_AI_API_KEY`, `JAMENDO_CLIENT_ID`, `FREESOUND_TOKEN`.

Défauts dans [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml) : `llm: openrouter`, `tts: smallest_ai` (ou silero/chatterbox/voice_studio), `image: local_sd`, `music: ambient_synth`, `publish: mock_publish`.

---

## 11. Artefacts & reprise

Tout est sous `pipeline/runs/<run_id>/` : `script/script.json`, `audio/episode.wav` + `speechplan.json`, `subtitles/subtitles.srt` (+ JSON par mot), `visual/world.json` + `scenes.json` + `assets/`, `video/episode.mp4` + `timecodes.txt` + `effects_report.json`, `metadata/metadata.json` + `thumbnail.png`.

En cas d’échec : `python -m core.cli resume ep-0001` — les étapes terminées sont ignorées, la reprise se fait au point exact.

---

## 12. Problèmes courants

| Symptôme | Cause | Solution |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg absent du PATH | Installer FFmpeg, relancer le terminal. |
| `CUDA out of memory` | SD dépasse la VRAM | Baisser la résolution (`image_size: [768, 432]`) ou provider externe. |
| `HTTP 429` | Quota fournisseur | Le router réessaie ou bascule sur `fallbacks:`. |
| `NameError` dans les tests | pipeline hors du path | Lancer `pytest` depuis la racine du dépôt. |

---

## 13. Statut & roadmap

- [x] Cœur M1–M4 ; métadonnées (S5) ; Web Studio ; doctor ; formats universels.
- [x] Image→vidéo par scène (Kling/fal_video ; live avec `FAL_KEY`).
- [x] Packaging cloud : Dockerfile + installateur systemd/Caddy.
- [ ] Production de séries en lot.

---

## 14. Documentation

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. Licence

**MIT** (voir [LICENSE](LICENSE)). Les composants liés à des modèles tiers (Silero, Coqui XTTS, Stable Diffusion) suivent leurs licences amont respectives.
