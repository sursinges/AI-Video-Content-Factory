# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | **Português (BR)** | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** é um sistema modular e aberto para produção de vídeo automatizada de ponta a ponta. Transforma temas, ideias ou roteiros prontos em vídeos completos: narração sincronizada, cenas animadas, mixagem ambiente, legendas e metadados de publicação.

O sistema é **universal**: **vídeos verticais curtos (9:16)**, **explicativos (16:9)**, **reviews de tecnologia**, **documentários educacionais** e **narrativas imersivas**.

---

## 1. O problema

Criar vídeo narrado exige malabarismo entre ferramentas: prompts e cenas cronometradas em LLMs; exportar locução e alinhar à mão; gerar ilustrações coerentes; editar (Ken Burns, crossfades, loudness); formatar legendas e metadados do YouTube. Se um passo falha, horas de trabalho se repetem. O **AI Video Content Factory** automatiza toda a cadeia num conveyor determinístico e reproduzível: em falha ou correção, continua do último estágio concluído — sem desperdiçar tokens nem re-renderizar o que já estava pronto.

---

## 2. Fluxo de produção

1. **Entrada:** tema, duração alvo, idioma e formato (ou seu próprio roteiro).
2. **M1 Roteiro:** estrutura em blocos com crítica dramática e fact-check.
3. **M2 Áudio:** síntese TTS com tags de emoção, normalização e timestamps por palavra via Whisper.
4. **M3 Visual:** limites de cena determinísticos (nas pausas da fala), restrições de mundo, geração de quadros.
5. **M4 Montagem:** movimento cinematográfico por cena, crossfades, masterização ambiente (−14 LUFS), legendas gravadas.
6. **M5 Metadados:** títulos, descrições, tags SEO, timecodes de capítulos, capa.
7. **M6 Publicação:** YouTube Data API v3 (ou exportação para pasta).

---

## 3. Capacidades principais

- **Local-first e offline:** modo mock totalmente offline ou modelos locais (Silero, Stable Diffusion) sem custos externos.
- **BYOK:** qualquer endpoint LLM compatível com OpenAI (OpenRouter, Groq…), TTS comercial (Smallest.ai, ElevenLabs) ou modelos de vídeo via `.env`.
- **Checkpoints e resume:** contratos JSON validados em SQLite (`state.db`); `pipeline resume <run_id>`.
- **Cache e orçamento:** chamadas cacheadas por hash; `budget_limit_usd` para antes de surpresas.
- **Ritmo inteligente:** cortes nunca no meio da palavra — alinhados às pausas detectadas pelo Whisper.
- **Duas interfaces:** CLI (`pipeline`) e Web Studio (`pipeline ui`) com storyboard interativo e prévia de cena.

---

## 4. Formatos

| Formato | Proporção | Resolução | Ritmo | Uso típico |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 s | Shorts/TikTok/Reels com legendas |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 s | Explicativos técnicos e de negócio |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 s | Reviews de hardware/software |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 s | Ciência, natureza, biografias |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 s | Comentários, monólogos |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 s | Histórias atmosféricas de fundo |

---

## 5. Funciona vs experimental

**Operacional:** conveyor M1–M5 com masterização real no FFmpeg; dry-run determinístico; state machine SQLite; CLI; interface em 10 idiomas; ambiente procedural + música CC0 (Openverse, Jamendo); legendas por palavra (`.srt` + burn-in); exportação para pasta própria; image→vídeo por cena (Kling via fal_video; ao vivo com `FAL_KEY`); prévia de cena com player no storyboard.

**Experimental:** Stable Diffusion local (FP16, NVIDIA ≥ 8 GB VRAM); clonagem local de voz (F5-TTS/Chatterbox, PyTorch CUDA); YouTube OAuth (M6, `client_secret.json`).

---

## 6. Edições: Desktop e Web (Cloud)

Uma base de código, duas edições (detalhes em [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)):

| | **Desktop** (Community) | **Web** (Cloud) |
|---|---|---|
| Usuários | um dono, sem login | multiusuário com login |
| Dados | workspace global | dados + BYOK por tenant |
| Faturamento | — | créditos por run, reembolso automático |
| Fila/quotas | — | fila de runs, quotas de disco |
| Modelos GPU locais | first-class (`pip install pipeline[desktop]`) | opcional |
| Instalação | `pip install pipeline[desktop]` → `pipeline ui` | deps base + `edition: web`, `hosted_mode: true` |

Detectada via `PIPELINE_EDITION` → `ui_settings.yaml` → padrão **desktop**; `pipeline doctor` informa.

---

## 7. Requisitos

**Mínimo (nuvem/API):** Windows 10/11, Ubuntu 22.04+ ou macOS; Python 3.11+; FFmpeg no PATH; 8 GB RAM; 5 GB de disco.
**Recomendado (local):** RTX 3060+ (8+ GB VRAM, CUDA 12.1+); 16 GB RAM; 30 GB SSD.

---

## 8. Instalação

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # se faltar: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. Primeiro uso

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # abre http://localhost:8765
```

---

## 10. Configuração e BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

Chaves em `pipeline/.env` (fora do git): `OPENROUTER_API_KEY`, opcionais `SMALLEST_AI_API_KEY`, `JAMENDO_CLIENT_ID`, `FREESOUND_TOKEN`.

Padrões em [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml): `llm: openrouter`, `tts: smallest_ai` (ou silero/chatterbox/voice_studio), `image: local_sd`, `music: ambient_synth`, `publish: mock_publish`.

---

## 11. Artefatos e resume

Tudo fica em `pipeline/runs/<run_id>/`: `script/script.json`, `audio/episode.wav` + `speechplan.json`, `subtitles/subtitles.srt` (+ JSON por palavra), `visual/world.json` + `scenes.json` + `assets/`, `video/episode.mp4` + `timecodes.txt` + `effects_report.json`, `metadata/metadata.json` + `thumbnail.png`.

Se algo falhar: `python -m core.cli resume ep-0001` — estágios concluídos são pulados e a execução retoma no ponto exato.

---

## 12. Problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg fora do PATH | Instalar FFmpeg e reabrir o terminal. |
| `CUDA out of memory` | SD não cabe na VRAM | Reduzir resolução (`image_size: [768, 432]`) ou usar provedor externo. |
| `HTTP 429` | Cota do provedor | O router tenta de novo ou cai no `fallbacks:`. |
| `NameError` nos testes | pipeline fora do path | Rodar `pytest` da raiz do repositório. |

---

## 13. Status e roadmap

- [x] Núcleo M1–M4; metadados (S5); Web Studio; doctor; formatos universais.
- [x] Image→vídeo por cena (Kling/fal_video; ao vivo com `FAL_KEY`).
- [x] Empacotamento cloud: Dockerfile + instalador systemd/Caddy.
- [ ] Produção de séries em lote.

---

## 14. Documentação

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. Licença

**MIT** (ver [LICENSE](LICENSE)). Componentes que integram modelos de terceiros (Silero, Coqui XTTS, Stable Diffusion) seguem as licenças upstream correspondentes.
