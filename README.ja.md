# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | **日本語** | [हिन्दी](README.hi.md) | [العربية](README.ar.md)

**AI Video Content Factory** は、エンドツーエンドの動画制作を自動化するオープンなモジュール式システムです。テーマ・アイデア・既存スクリプトから、同期されたナレーション、アニメーションするシーン映像、アンビエントミックス、字幕、公開用メタデータまでを含む完成動画を作ります。

**汎用**設計：**縦型ショート動画（9:16）**、**解説動画（16:9）**、**テックレビュー**、**教育ドキュメンタリー**、**没入型ナラティブ**に対応。

---

## 1. 解決する課題

ナレーション動画の制作は通常、分断されたツールの往復です：LLMでプロンプトとシーン分割、音声合成の書き出しと手動同期、一貫性のあるシーン画像の生成、エディタでの編集（Ken Burns、クロスフェード、ラウドネス）、字幕とYouTubeメタデータの整形。途中で失敗したり修正が要ると、数時間やり直し。**AI Video Content Factory** はこの一連の流れを決定論的で再現可能なパイプラインに自動化します。中断やシーン修正の際は、完了済みステージから再開——トークンを無駄にせず、済み部分は再レンダリングしません。

---

## 2. 制作フロー

1. **入力：** トピック、目標長、言語、フォーマット（または自作スクリプト）。
2. **M1 脚本：** 演出チェック・ファクトチェック付きの構造化チャンク。
3. **M2 音声：** 感情タグ付きTTS、ラウドネス正規化、Whisperによる単語レベルタイムスタンプ。
4. **M3 ビジュアル：** 発話の休止に合わせた決定論的シーン分割、世界設定の制約、画像生成。
5. **M4 編集：** シーンごとのカメラワーク、クロスフェード、アンビエントマスタリング（−14 LUFS）、字幕焼き込み。
6. **M5 メタデータ：** タイトル、説明、SEOタグ、チャプターtimecode、サムネイル。
7. **M6 公開：** YouTube Data API v3（またはフォルダ書き出し）。

---

## 3. 主な機能

- **ローカルファースト・オフライン対応：** mockモードは完全オフライン、またはローカルモデル（Silero TTS、ローカルStable Diffusion）で外部課金ゼロ。
- **BYOK：** OpenAI互換の任意LLM（OpenRouter、Groqなど）、商用TTS（Smallest.ai、ElevenLabs）、動画モデルを `.env` で接続。
- **チェックポイント＆再開：** 各ステージは検証済みJSON契約をSQLite（`state.db`）とディスクに保存。`pipeline resume <run_id>` で中断箇所から続行。
- **キャッシュと予算：** 呼び出しはハッシュでキャッシュ。`budget_limit_usd` で高額実行を未然に停止。
- **スマートなテンポ：** カットは単語の途中に入らない——Whisperが検出した発話の休止にスナップ。
- **2つのインターフェース：** CLI（`pipeline`）とWeb Studio（`pipeline ui`）——インタラクティブ絵コンテとシーンプレビュープレイヤー付き。

---

## 4. フォーマット

| フォーマット | 比率 | 解像度 | テンポ | 典型的用途 |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 秒 | Shorts/TikTok/Reels（焼き込み字幕） |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 秒 | 技術・ビジネス解説 |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 秒 | ハード・ソフトのレビュー |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 秒 | 科学・自然・人物伝 |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 秒 | コメント、モノローグ |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 秒 | 聴き流す向けの静かな物語 |

---

## 5. 実装済み vs 実験的

**動作済み：** M1–M5の本番FFmpegマスタリング；決定論的dry-run；SQLiteステートマシン；CLI；10言語UI；手続き的アンビエント＋CC0音楽（Openverse、Jamendo）；単語レベル字幕（`.srt`＋焼き込み）；カスタムフォルダ書き出し；シーン単位のimage→video（fal_video経由でKling。ライブは `FAL_KEY` が必要）；絵コンテ内のシーンプレビュープレイヤー。

**実験的：** ローカルStable Diffusion（FP16、NVIDIA ≥ 8 GB VRAM）；ローカル音声クローン（F5-TTS/Chatterbox、PyTorch CUDA）；YouTube OAuth（M6、`client_secret.json`）。

---

## 6. エディション：Desktop と Web（クラウド）

同一コードベース、2つのエディション（詳細は [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)）：

| | **Desktop**（Community、既定） | **Web**（クラウド） |
|---|---|---|
| ユーザー | 一所有者、サインイン不要 | マルチテナント、サインイン必須 |
| データ | 共有ワークスペース | テナント分離データ＋テナントBYOK |
| 課金 | — | 実行ごとにクレジット、失敗時自動返金 |
| キュー/割当 | — | 実行キュー、ディスク割当 |
| ローカルGPUモデル | ファーストクラス（`pip install pipeline[desktop]`） | 任意 |
| 導入 | `pip install pipeline[desktop]` → `pipeline ui` | 基本依存 + `edition: web`、`hosted_mode: true` |

エディションは `PIPELINE_EDITION` → `ui_settings.yaml` → 既定 **desktop** の順で判定。`pipeline doctor` が表示します。

---

## 7. システム要件

**最小（クラウド/API モード）：** Windows 10/11、Ubuntu 22.04+、macOS；Python 3.11+；PATH上のFFmpeg；RAM 8 GB；ディスク 5 GB。
**推奨（ローカル生成）：** RTX 3060+（8+ GB VRAM、CUDA 12.1+）；RAM 16 GB+；SSD 30 GB。

---

## 8. インストール

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # 無ければ: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. 初回実行

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # http://localhost:8765 を開く
```

---

## 10. 設定と BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

キーは `pipeline/.env`（git対象外）に：`OPENROUTER_API_KEY`、任意で `SMALLEST_AI_API_KEY`、`JAMENDO_CLIENT_ID`、`FREESOUND_TOKEN`。

既定プロバイダーは [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml)：`llm: openrouter`、`tts: smallest_ai`（silero/chatterbox/voice_studio も可）、`image: local_sd`、`music: ambient_synth`、`publish: mock_publish`。

---

## 11. 成果物と再開

成果物は `pipeline/runs/<run_id>/` に：`script/script.json`、`audio/episode.wav` + `speechplan.json`、`subtitles/subtitles.srt`（+単語JSON）、`visual/world.json` + `scenes.json` + `assets/`、`video/episode.mp4` + `timecodes.txt` + `effects_report.json`、`metadata/metadata.json` + `thumbnail.png`。

失敗時：`python -m core.cli resume ep-0001` — 完了済みステージをスキップし、失敗箇所から正確に再開。

---

## 12. トラブルシューティング

| 症状 | 原因 | 解決 |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg未導入またはPATH外 | FFmpegを導入しターミナルを再起動。 |
| `CUDA out of memory` | SDがVRAMを超過 | 解像度を下げる（`image_size: [768, 432]`）か外部画像プロバイダーへ。 |
| `HTTP 429` | プロバイダー制限 | ルーターが自動リトライ、`fallbacks:` に切替。 |
| テストで `NameError` | pipelineがPython path外 | リポジトリのルートで `pytest` を実行。 |

---

## 13. ステータスとロードマップ

- [x] コアパイプライン M1–M4；メタデータ（S5）；Web Studio；doctor；汎用フォーマット。
- [x] シーン単位のimage→video（Kling/fal_video；ライブは `FAL_KEY`）。
- [x] クラウドパッケージング：Dockerfile + systemd/Caddyインストーラ。
- [ ] シリーズ一括生成。

---

## 14. ドキュメント

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. ライセンス

**MIT**（[LICENSE](LICENSE) 参照）。サードパーティモデルを利用するコンポーネント（Silero、Coqui XTTS、Stable Diffusion）は各上流ライセンスに従います。
