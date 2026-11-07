# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [हिन्दी](README.hi.md) | **العربية**

**AI Video Content Factory** نظام مفتوح ومعياري لإنتاج الفيديو المؤتمت من البداية إلى النهاية. يحوّل المواضيع والأفكار أو النصوص الجاهزة إلى فيديو مكتمل: تعليق صوتي متزامن، مشاهد متحركة، مزيج صوتي محيطي، ترجمات، وبيانات وصفية للنشر.

النظام **عالمي**: **فيديوهات عمودية قصيرة (9:16)**، **فيديوهات توضيحية (16:9)**، **مراجعات تقنية**، **وثائقيات تعليمية**، و**سرد غامر**.

---

## 1. المشكلة التي يحلها

صناعة فيديو بتعليق صوتي تعني عادة التنقل بين أدوات متفرقة: كتابة الأوامر وتقسيم النص إلى مشاهد موقّتة في نماذج LLM؛ تصدير الصوت من مولدات الكلام ومواءمته يدويًا؛ توليد رسومات متسقة للمشاهد؛ المونتاج (Ken Burns والتلاشي وموازنة الصوت)؛ ثم تنسيق الترجمة وبيانات YouTube. عند فشل أي خطوة تتكرر ساعات من العمل. **AI Video Content Factory** يؤتمت السلسلة كاملة في خط إنتاج حتمي قابل للتكرار: عند الانقطاع أو تعديل مشهد يكمل من آخر مرحلة مكتملة — دون هدر رموز API أو إعادة رندر ما أُنجز.

---

## 2. سير الإنتاج

1. **المدخل:** الموضوع، المدة المستهدفة، اللغة، الصيغة (أو نصك الخاص).
2. **M1 النص:** هيكلة إلى مقاطع مع نقد درامي وفحص حقائق.
3. **M2 الصوت:** توليد تعليق بوسوم عاطفية، معايرة الصوت، وطوابع زمنية لكل كلمة عبر Whisper.
4. **M3 المرئيات:** حدود مشاهد حتمية على وقفات الكلام، قيود العالم (الألوان/الإضاءة)، توليد الإطارات.
5. **M4 المونتاج:** حركة كاميرا سينمائية لكل مشهد، تلاشٍ متقاطع، معايرة الموسيقى (−14 LUFS)، حرق الترجمة.
6. **M5 البيانات الوصفية:** عناوين، أوصاف، وسوم SEO، طوابع الفصول، صورة الغلاف.
7. **M6 النشر:** YouTube Data API v3 (أو تصدير إلى مجلد).

---

## 3. القدرات الأساسية

- **محلي أولًا ويعمل دون اتصال:** وضع mock كامل دون إنترنت، أو نماذج محلية (Silero TTS، Stable Diffusion المحلي) دون تكاليف خارجية.
- **BYOK:** أي نقطة LLM متوافقة مع OpenAI (OpenRouter وGroq وغيرها)، TTS تجاري (Smallest.ai وElevenLabs)، أو نماذج فيديو عبر `.env`.
- **نقاط فحص واستئناف:** كل مرحلة تحفظ عقود JSON متحققًا منها في SQLite (`state.db`)؛ `pipeline resume <run_id>` يكمل من نقطة التوقف.
- **ذاكرة مؤقتة وميزانيات:** استدعاءات مخبأة بالهاش؛ `budget_limit_usd` يوقف قبل المفاجآت المكلفة.
- **إيقاع ذكي:** القطع لا تقع وسط الكلمة أبدًا — تلتصق بوقفات الكلام.
- **واجهتان:** CLI (`pipeline`) وWeb Studio (`pipeline ui`) بلوحة مشاهد تفاعلية ومشغّل معاينة لكل مشهد.

---

## 4. الصيغ

| الصيغة | النسبة | الدقة | إيقاع المشاهد | الاستخدام |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 ث | Shorts/TikTok/Reels بترجمة محروقة |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 ث | شروحات تقنية وأعمال |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 ث | مراجعات أجهزة وبرمجيات |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 ث | علوم وطبيعة وسير |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 ث | تعليق ومونولوج |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 ث | حكايات هادئة للاستماع الخلفي |

---

## 5. الجاهز مقابل التجريبي

**يعمل:** خط الإنتاج M1–M5 بمعالجة FFmpeg حقيقية؛ وضع dry-run حتمي؛ آلة حالات SQLite؛ واجهة CLI؛ واجهة بعشر لغات؛ موسيقى محيطية إجرائية + CC0 (Openverse وJamendo)؛ ترجمة كلمة بكلمة (`.srt` وحرق بأساليب)؛ تصدير لمجلد مخصص؛ image→video لكل مشهد (Kling عبر fal_video؛ التشغيل الفعلي بمفتاح `FAL_KEY`)؛ مشغّل معاينة المشهد داخل لوحة المشاهد.

**تجريبي:** Stable Diffusion المحلي (FP16، NVIDIA ≥ 8 GB VRAM)؛ استنساخ الصوت محليًا (F5-TTS/Chatterbox، PyTorch CUDA)؛ YouTube OAuth (M6، `client_secret.json`).

---

## 6. النسختان: Desktop وWeb (السحابة)

قاعدة كود واحدة ونسختان (التفاصيل في [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)):

| | **Desktop** (Community، الافتراضية) | **Web** (السحابة) |
|---|---|---|
| المستخدمون | مالك واحد بدون تسجيل دخول | متعدد المستأجرين مع بوابة دخول |
| البيانات | مساحة عمل عامة | بيانات معزولة لكل مستأجر + BYOK |
| الفوترة | — | أرصدة لكل تشغيل واسترداد تلقائي عند الفشل |
| الطابور/الحصص | — | طابور تشغيل وحصص قرص |
| نماذج GPU المحلية | بمستوى أول (`pip install pipeline[desktop]`) | اختيارية |
| التثبيت | `pip install pipeline[desktop]` → `pipeline ui` | الاعتماديات الأساسية + `edition: web` و`hosted_mode: true` |

تُحدد النسخة من `PIPELINE_EDITION` ← `ui_settings.yaml` ← الافتراضي **desktop**؛ ويعرضها `pipeline doctor`.

---

## 7. متطلبات النظام

**الحد الأدنى (سحابي/API):** ويندوز 10/11 أو أوبونتو 22.04+ أو macOS؛ بايثون 3.11+؛ FFmpeg في PATH؛ ذاكرة 8 GB؛ قرص 5 GB.
**الموصى به (توليد محلي):** RTX 3060+ (8+ GB VRAM، CUDA 12.1+)؛ ذاكرة 16 GB+؛ قرص SSD 30 GB.

---

## 8. التثبيت خطوة بخطوة

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # إن غاب: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. أول تشغيل

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # افتح http://localhost:8765
```

---

## 10. الإعداد وBYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

المفاتيح في `pipeline/.env` (خارج git): `OPENROUTER_API_KEY`، واختياريًا `SMALLEST_AI_API_KEY` و`JAMENDO_CLIENT_ID` و`FREESOUND_TOKEN`.

الافتراضيات في [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml): `llm: openrouter`، `tts: smallest_ai` (أو silero/chatterbox/voice_studio)، `image: local_sd`، `music: ambient_synth`، `publish: mock_publish`.

---

## 11. المخرجات والاستئناف

كل شيء تحت `pipeline/runs/<run_id>/`: `script/script.json`، `audio/episode.wav` + `speechplan.json`، `subtitles/subtitles.srt` (+JSON للكلمات)، `visual/world.json` + `scenes.json` + `assets/`، `video/episode.mp4` + `timecodes.txt` + `effects_report.json`، `metadata/metadata.json` + `thumbnail.png`.

عند الفشل: `python -m core.cli resume ep-0001` — تُتخطى المراحل المكتملة ويُستأنف من نقطة الفشل بدقة.

---

## 12. مشاكل شائعة

| العرض | السبب | الحل |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg غير مثبت أو خارج PATH | ثبّت FFmpeg وأعد فتح الطرفية. |
| `CUDA out of memory` | SD يتجاوز ذاكرة الرسوم | اخفض الدقة (`image_size: [768, 432]`) أو استخدم مزودًا خارجيًا. |
| `HTTP 429` | حصة المزود | يعيد الموجّه المحاولة أو ينتقل إلى `fallbacks:`. |
| `NameError` في الاختبارات | pipeline خارج مسار بايثون | شغّل `pytest` من جذر المستودع. |

---

## 13. الحالة وخارطة الطريق

- [x] النواة M1–M4؛ البيانات الوصفية (S5)؛ Web Studio؛ doctor؛ صيغ عالمية.
- [x] image→video لكل مشهد (Kling/fal_video؛ الفعلي بمفتاح `FAL_KEY`).
- [x] تغليف سحابي: Dockerfile + مثبّت systemd/Caddy.
- [ ] إنتاج المسلسلات بالدفعات.

---

## 14. الوثائق

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. الترخيص

**MIT** (انظر [LICENSE](LICENSE)). المكونات المرتبطة بنماذج أطراف ثالثة (Silero وCoqui XTTS وStable Diffusion) تخضع لتراخيص أصحابها.
