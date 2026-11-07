# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | **Español** | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** es un sistema modular y abierto para producción de vídeo automatizada de extremo a extremo. Convierte temas, ideas o guiones existentes en vídeos completos narrados, con locución sincronizada, escenas animadas, mezcla de ambiente, subtítulos y metadatos de publicación.

Es **universal**: soporta varios formatos — **vídeos verticales cortos (9:16)**, **explicativos (16:9)**, **reseñas de tecnología**, **documentales educativos** y **narrativas envolventes**.

---

## 1. El problema

Crear vídeo narrado implica malabares con herramientas sueltas: prompts y escenas temporizadas en LLMs; exportar locuciones y alinearlas a mano; generar ilustraciones coherentes; montar en el editor (Ken Burns, fundidos, volumen); formatear subtítulos y metadatos de YouTube. Si un paso falla, se rehacen horas de trabajo. **AI Video Content Factory** automatiza toda la cadena en un conveyor determinista y reproducible: ante un fallo o una corrección, continúa desde el últimoStage completado sin gastar tokens ni re-renderizar lo ya hecho.

---

## 2. Flujo de producción

1. **Entrada:** tema, duración objetivo, idioma y formato (o tu propio guion).
2. **M1 Guion:** estructura en fragmentos con crítica dramática y fact-check.
3. **M2 Audio:** síntesis TTS con etiquetas de emoción, normalización y marcas de palabra vía Whisper.
4. **M3 Visual:** límites de escena deterministas (en pausas del habla), restricciones de mundo, generación de fotogramas.
5. **M4 Ensamblado:** movimiento cinematográfico por escena, fundidos, ambient a −14 LUFS, subtítulos incrustados.
6. **M5 Metadatos:** títulos, descripciones, tags SEO, timecodes y miniatura.
7. **M6 Publicación:** YouTube Data API v3 (o exportación a carpeta).

---

## 3. Capacidades clave

- **Local-first y offline:** modo mock totalmente offline o modelos locales (Silero, Stable Diffusion) sin costes externos.
- **BYOK:** cualquier endpoint LLM OpenAI-compatible (OpenRouter, Groq…), TTS comercial (Smallest.ai, ElevenLabs) o modelos de vídeo vía `.env`.
- **Checkpoints y resume:** cada etapa guarda contratos JSON validados en SQLite (`state.db`); `pipeline resume <run_id>` continúa donde paró.
- **Caché y presupuestos:** llamadas cacheadas por hash; `budget_limit_usd` frena antes de sustos.
- **Ritmo inteligente:** los cortes nunca parten palabras — se ajustan a pausas detectadas por Whisper.
- **Doble interfaz:** CLI (`pipeline`) y Web Studio (`pipeline ui`) con storyboard interactivo y vista previa de escena.

---

## 4. Formatos

| Formato | Ratio | Resolución | Ritmo | Uso típico |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 seg | Shorts, TikTok, Reels con subtítulos |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 seg | Explicativos técnicos y de negocio |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 seg | Reseñas de hardware/software |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 seg | Ciencia, naturaleza, biografías |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 seg | Comentario, monólogos |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 seg | Historias atmosféricas de fondo |

---

## 5. Funciona vs experimental

### Operativo
- Conveyor completo M1–M5 con masterización real en FFmpeg.
- Dry-run determinista (mocks sintéticos en segundos).
- State machine SQLite; CLI (`doctor`, `run`, `status`, `resume`, `ui`).
- Interfaz en 10 idiomas; ambient procedural y música CC0 (Openverse, Jamendo).
- Subtítulos por palabra (`.srt` y burn-in); exportación a carpeta propia.
- Image→video por escenas (Kling vía fal_video; live con `FAL_KEY`).
- Vista previa de escena con reproductor en el storyboard.

### Experimental
- **Stable Diffusion local (FP16):** NVIDIA ≥ 8 GB VRAM.
- **Clonación local de voz (F5-TTS / Chatterbox):** PyTorch CUDA + pesos.
- **YouTube OAuth (M6):** Google Cloud OAuth Client (`client_secret.json`).

---

## 6. Ediciones: Desktop y Web (Cloud)

Una base de código, dos ediciones (detalle en [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)):

| | **Desktop** (Community) | **Web** (Cloud) |
|---|---|---|
| Usuarios | un propietario, sin login | multiusuario con login |
| Datos | workspace global | datos y BYOK por tenant |
| Facturación | — | créditos por run, reembolso automático |
| Cola / cuotas | — | cola de runs, cuotas de disco |
| Modelos GPU locales | first-class (`pip install pipeline[desktop]`) | opcional |
| Instalación | `pip install pipeline[desktop]` → `pipeline ui` | deps base + `edition: web`, `hosted_mode: true` |

Detectada desde `PIPELINE_EDITION` → `ui_settings.yaml` → por defecto **desktop**; `pipeline doctor` la informa.

---

## 7. Requisitos

**Mínimo (nube/API):** Windows 10/11, Ubuntu 22.04+ o macOS; Python 3.11+; FFmpeg en PATH; 8 GB RAM; 5 GB disco.
**Recomendado (local):** RTX 3060+ (8+ GB VRAM, CUDA 12.1+); 16 GB RAM; 30 GB SSD.

---

## 8. Instalación

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # si falta: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. Primer arranque

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # abre http://localhost:8765
```

---

## 10. Configuración y BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

Claves en `pipeline/.env` (fuera de git):
```env
OPENROUTER_API_KEY="sk-or-v1-..."
SMALLEST_AI_API_KEY="..."
JAMENDO_CLIENT_ID="..."
FREESOUND_TOKEN="..."
```

Defaults en [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml): `llm: openrouter`, `tts: smallest_ai` (o silero/chatterbox/voice_studio), `image: local_sd`, `music: ambient_synth`, `publish: mock_publish`.

---

## 11. Artefactos y resume

Todo queda en `pipeline/runs/<run_id>/`: `script/script.json`, `audio/episode.wav` + `speechplan.json`, `subtitles/subtitles.srt` (+ JSON por palabra), `visual/world.json` + `scenes.json` + `assets/`, `video/episode.mp4` + `timecodes.txt` + `effects_report.json`, `metadata/metadata.json` + `thumbnail.png`.

Si algo falla: `python -m core.cli resume ep-0001` — se saltan las etapas completadas y continúa en el punto exacto.

---

## 12. Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg no está en PATH | Instalar FFmpeg y reiniciar terminal. |
| `CUDA out of memory` | SD no cabe en VRAM | Bajar resolución (`image_size: [768, 432]`) o usar proveedor externo. |
| `HTTP 429` | Cuota del proveedor | El router reintenta o cae al `fallbacks:`. |
| `NameError` en tests | pipeline fuera del path | Ejecutar `pytest` desde la raíz del repo. |

---

## 13. Estado y roadmap

- [x] Núcleo M1–M4; metadatos (S5); Web Studio; doctor; formatos universales.
- [x] Image→video por escena (Kling/fal_video; live con `FAL_KEY`).
- [x] Empaquetado cloud: Dockerfile + instalador systemd/Caddy.
- [ ] Producción de series en lote.

---

## 14. Documentación

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. Licencia

**MIT** (ver [LICENSE](LICENSE)). Los componentes que enlazan modelos de terceros (Silero, Coqui XTTS, Stable Diffusion) se rigen por sus licencias originales.
