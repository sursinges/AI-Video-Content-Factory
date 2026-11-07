# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt-BR.md) | **中文** | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** 是一个开放、模块化的端到端自动化视频生产系统。它将主题、想法或现成脚本转化为完整成片：同步配音、动态场景画面、环境音混音、字幕以及发布元数据。

系统是**通用**的：支持**竖屏短视频（9:16）**、**解释类视频（16:9）**、**科技评测**、**教育纪录片**和**沉浸式叙事**。

---

## 1. 解决什么问题

制作一条叙事视频通常要在多个割裂的工具间来回：在 LLM 里写提示词并按时间切分场景；从语音合成器导出配音并手动对齐；生成风格一致的场景插图；在剪辑软件里拼接（Ken Burns、交叉溶解、响度平衡）；再排版字幕和 YouTube 元数据。任何一步失败或需要小改，都得重做几小时。**AI Video Content Factory** 把整条链路自动化为确定性、可复现的流水线：中断或修改某一场景时，从最后一个完成的阶段继续——不浪费 API 令牌，也不重渲染已完成的内容。

---

## 2. 端到端流程

1. **输入：** 主题、目标时长、语言与格式（或你自己的脚本）。
2. **M1 脚本：** 结构化分块，附带戏剧性评审、节奏检查与事实核查。
3. **M2 音频：** 带情感标签的 TTS 合成、响度归一，并经 Whisper 得到词级时间戳。
4. **M3 视觉：** 确定性场景边界（对齐语音停顿）、世界约束（配色/光线）、场景画面生成。
5. **M4 合成：** 每场景镜头运动、交叉溶解、环境音母带处理（−14 LUFS）、字幕烧录。
6. **M5 元数据：** 标题、描述、SEO 标签、章节时间码、封面。
7. **M6 发布：** YouTube Data API v3（或导出到文件夹）。

---

## 3. 核心能力

- **本地优先、可离线：** mock 模式完全离线，或使用本地模型（Silero TTS、本地 Stable Diffusion），零外部费用。
- **BYOK：** 任意 OpenAI 兼容 LLM（OpenRouter、Groq 等）、商业 TTS（Smallest.ai、ElevenLabs）或视频模型，经 `.env` 接入。
- **检查点与续跑：** 每阶段把校验过的 JSON 契约写入 SQLite（`state.db`）；`pipeline resume <run_id>` 从断点继续。
- **缓存与预算：** 调用按哈希缓存；`budget_limit_usd` 在意外开销前刹车。
- **智能节奏：** 剪切永不切在词中间——对齐 Whisper 检测到的语音停顿。
- **双界面：** CLI（`pipeline`）与 Web Studio（`pipeline ui`），交互式分镜、模型选择、场景预览播放器。

---

## 4. 格式

| 格式 | 比例 | 分辨率 | 场景节奏 | 典型用途 |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 秒 | Shorts/TikTok/Reels（烧录字幕） |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 秒 | 技术与商业解释 |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 秒 | 软硬件评测 |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 秒 | 科学、自然、传记 |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 秒 | 评论、独白 |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 秒 | 背景向舒缓叙事 |

---

## 5. 已实现 vs 实验性

**已实现：** M1–M5 全流程真实 FFmpeg 母带处理；确定性 dry-run；SQLite 状态机；CLI（doctor/run/status/resume/ui）；10 语言界面；程序化环境音 + CC0 音乐（Openverse、Jamendo）；词级字幕（`.srt` 与烧录）；自定义导出目录；按场景 image→video（经 fal_video 使用 Kling；live 需 `FAL_KEY`）；分镜中的场景预览播放器。

**实验性：** 本地 Stable Diffusion（FP16，NVIDIA ≥ 8 GB VRAM）；本地声音克隆（F5-TTS/Chatterbox，PyTorch CUDA）；YouTube OAuth（M6，`client_secret.json`）。

---

## 6. 版本：Desktop 与 Web（云）

同一套代码，两个版本（详见 [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)）：

| | **Desktop**（Community，默认） | **Web**（云） |
|---|---|---|
| 用户 | 单所有者，无登录 | 多租户，需登录 |
| 数据 | 全局工作区 | 租户隔离数据 + 租户 BYOK |
| 计费 | — | 每次运行扣积分，失败自动退还 |
| 队列/配额 | — | 运行队列、磁盘配额 |
| 本地 GPU 模型 | 一等公民（`pip install pipeline[desktop]`） | 可选 |
| 安装 | `pip install pipeline[desktop]` → `pipeline ui` | 基础依赖 + `edition: web`、`hosted_mode: true` |

版本经 `PIPELINE_EDITION` 环境变量 → `ui_settings.yaml` → 默认 **desktop**；`pipeline doctor` 会报告。

---

## 7. 系统要求

**最低（云/API 模式）：** Windows 10/11、Ubuntu 22.04+ 或 macOS；Python 3.11+；FFmpeg 在 PATH；8 GB 内存；5 GB 磁盘。
**推荐（本地生成）：** RTX 3060+（8+ GB VRAM，CUDA 12.1+）；16 GB+ 内存；30 GB SSD。

---

## 8. 安装

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # 若缺失：winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. 首次运行

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # 打开 http://localhost:8765
```

---

## 10. 配置与 BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

密钥放在 `pipeline/.env`（不入 git）：`OPENROUTER_API_KEY`，可选 `SMALLEST_AI_API_KEY`、`JAMENDO_CLIENT_ID`、`FREESOUND_TOKEN`。

默认提供方在 [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml)：`llm: openrouter`，`tts: smallest_ai`（或 silero/chatterbox/voice_studio），`image: local_sd`，`music: ambient_synth`，`publish: mock_publish`。

---

## 11. 产物与续跑

所有产物位于 `pipeline/runs/<run_id>/`：`script/script.json`，`audio/episode.wav` + `speechplan.json`，`subtitles/subtitles.srt`（+词级 JSON），`visual/world.json` + `scenes.json` + `assets/`，`video/episode.mp4` + `timecodes.txt` + `effects_report.json`，`metadata/metadata.json` + `thumbnail.png`。

失败时：`python -m core.cli resume ep-0001`——跳过已完成阶段，从故障点精确继续。

---

## 12. 常见问题

| 症状 | 原因 | 解决 |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg 不在 PATH | 安装 FFmpeg 并重启终端。 |
| `CUDA out of memory` | SD 超出显存 | 降低分辨率（`image_size: [768, 432]`）或用外部图像提供方。 |
| `HTTP 429` | 提供方限额 | 路由器自动重试或回退到 `fallbacks:`。 |
| 测试 `NameError` | pipeline 不在 Python path | 从仓库根目录运行 `pytest`。 |

---

## 13. 状态与路线图

- [x] 核心流水线 M1–M4；元数据（S5）；Web Studio；doctor；通用格式。
- [x] 按场景 image→video（Kling/fal_video；live 需 `FAL_KEY`）。
- [x] 云端打包：Dockerfile + systemd/Caddy 安装脚本。
- [ ] 批量系列生产。

---

## 14. 文档

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. 许可证

**MIT**（见 [LICENSE](LICENSE)）。链接第三方模型的组件（Silero、Coqui XTTS、Stable Diffusion）遵循各自的上游许可。
