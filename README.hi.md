# AI Video Content Factory

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Português](README.pt-BR.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | **हिन्दी** | [العربية](README.ar.md)

**AI Video Content Factory** स्वचालित, एंड-टू-एंड वीडियो निर्माण की एक खुली मॉड्यूलर प्रणाली है। यह विषयों, विचारों या मौजूदा स्क्रिप्ट को पूरी तरह तैयार वीडियो में बदलती है: सिंक्रनाइज़्ड वॉइसओवर, एनिमेटेड सीन विज़ुअल्स, एम्बिएंट मिक्स, सबटाइटल और पब्लिशिंग मेटाडेटा।

प्रणाली **सार्वभौमिक** है: **वर्टिकल शॉर्ट्स (9:16)**, **एक्सप्लेनर (16:9)**, **टेक रिव्यू**, **शैक्षिक डॉक्यूमेंट्री** और **इमर्सिव नैरेटिव**।

---

## 1. समस्या

नैरेटेड वीडियो बनाने में आमतौर पर कई अलग-अलग टूल्स के बीच झूलना पड़ता है: LLM में प्रॉम्प्ट और सीन टाइमिंग; स्पीच सिंथेसाइज़र से वॉइसओवर निकालकर मैन्युअल अलाइन करना; मेल खाते सीन इलस्ट्रेशन बनाना; एडिटर में असेंबली (Ken Burns, क्रॉसफ़ेड, लाउडनेस); सबटाइटल और YouTube मेटाडेटा तैयार करना। कोई बीच का चरण फेल हो या छोटा बदलाव करना हो, तो घंटों का काम दोबारा। **AI Video Content Factory** पूरी श्रृंखला को एक निर्धारक, प्रजननयोग्य कन्वेयर में स्वचालित करती है: रुकावट या सीन-संशोधन पर सिस्टम आख़िरी पूर्ण स्टेज से आगे बढ़ता है — टोकन बर्बाद किए बिना, तैयार मीडिया दोबारा रेंडर किए बिना।

---

## 2. वर्कफ़्लो

1. **इनपुट:** विषय, लक्ष्य अवधि, भाषा, फ़ॉर्मेट (या अपनी स्क्रिप्ट)।
2. **M1 स्क्रिप्ट:** ड्रामा-समीक्षा, पेसिंग जांच और फैक्ट-चेक के साथ संरचित चंक्स।
3. **M2 ऑडियो:** इमोशन टैग के साथ TTS, लाउडनेस नॉर्मलाइज़ेशन, Whisper से शब्द-स्तरीय टाइमस्टैम्प।
4. **M3 विज़ुअल:** स्पीच-पॉज़ पर स्नैप होती सीन सीमाएँ, वर्ल्ड रेस्ट्रिक्शन्स, फ़्रेम जनरेशन।
5. **M4 असेंबली:** सीन-वार कैमरा मूवमेंट, क्रॉसफ़ेड, एम्बिएंट मास्टरिंग (−14 LUFS), सबटाइटल बर्न-इन।
6. **M5 मेटाडेटा:** टाइटल, विवरण, SEO टैग, चैप्टर टाइमकोड, थंबनेल।
7. **M6 पब्लिश:** YouTube Data API v3 (या फ़ोल्डर एक्सपोर्ट)।

---

## 3. मुख्य क्षमताएँ

- **लोकल-फ़र्स्ट और ऑफ़लाइन:** mock मोड पूरी तरह ऑफ़लाइन, या लोकल मॉडल (Silero TTS, लोकल Stable Diffusion) — बाहरी खर्च शून्य।
- **BYOK:** कोई भी OpenAI-कम्पैटिबल LLM (OpenRouter, Groq…), कमर्शियल TTS (Smallest.ai, ElevenLabs) या वीडियो मॉडल `.env` से।
- **चेकपॉइंट और रिज़्यूम:** हर स्टेज सत्यापित JSON कॉन्ट्रैक्ट SQLite (`state.db`) और डिस्क में सेव करता है; `pipeline resume <run_id>` से ठीक रुके स्थान से आगे।
- **कैश और बजट:** कॉल हैश-कैश्ड; `budget_limit_usd` महँगी गड़बड़ी से पहले रोकता है।
- **स्मार्ट पेसिंग:** कट कभी शब्द के बीच नहीं — Whisper-पॉज़ पर स्नैप।
- **दो इंटरफ़ेस:** CLI (`pipeline`) और Web Studio (`pipeline ui`) — इंटरैक्टिव स्टोरीबोर्ड और सीन प्रीव्यू प्लेयर के साथ।

---

## 4. फ़ॉर्मेट

| फ़ॉर्मेट | अनुपात | रिज़ॉल्यूशन | गति | उपयोग |
|---|---|---|---|---|
| `short_vertical` | **9:16** | 1080x1920 | 3 – 7 से | Shorts/TikTok/Reels (बर्न-इन सबटाइटल) |
| `explainer` | **16:9** | 1920x1080 | 6 – 12 से | तकनीकी व बिज़नेस एक्सप्लेनर |
| `tech_review` | **16:9** | 1920x1080 | 5 – 10 से | हार्डवेयर/सॉफ़्टवेयर रिव्यू |
| `educational_narrative` | **16:9** | 1920x1080 | 12 – 25 से | विज्ञान, प्रकृति, जीवनियाँ |
| `talking_head` | **16:9** | 1920x1080 | 8 – 15 से | कमेंट्री, मोनोलॉग |
| `long_narrative` | **16:9** | 1920x1080 | 30 – 60 से | बैकग्राउंड देखने हेतु शांत कथाएँ |

---

## 5. कार्यशील बनाम प्रयोगात्मक

**कार्यशील:** M1–M5 कन्वेयर वास्तविक FFmpeg मास्टरिंग के साथ; निर्धारक dry-run; SQLite स्टेट-मशीन; CLI; 10 भाषाओं में UI; प्रोसीजरल एम्बिएंट + CC0 संगीत (Openverse, Jamendo); शब्द-स्तरीय सबटाइटल (`.srt` + बर्न-इन); कस्टम फ़ोल्डर एक्सपोर्ट; सीन-वार image→video (fal_video से Kling; लाइव हेतु `FAL_KEY`); स्टोरीबोर्ड में सीन प्रीव्यू प्लेयर।

**प्रयोगात्मक:** लोकल Stable Diffusion (FP16, NVIDIA ≥ 8 GB VRAM); लोकल वॉइस क्लोनिंग (F5-TTS/Chatterbox, PyTorch CUDA); YouTube OAuth (M6, `client_secret.json`)।

---

## 6. संस्करण: Desktop और Web (Cloud)

एक कोडबेस, दो संस्करण (विवरण: [`pipeline/docs/EDITIONS.md`](pipeline/docs/EDITIONS.md)):

| | **Desktop** (Community, डिफ़ॉल्ट) | **Web** (Cloud) |
|---|---|---|
| उपयोगकर्ता | एक मालिक, साइन-इन नहीं | मल्टी-टेनेंट, साइन-इन गेट |
| डेटा | ग्लोबल वर्कस्पेस | टेनेंट-अलग डेटा + टेनेंट BYOK |
| बिलिंग | — | प्रति रन क्रेडिट, विफलता पर ऑटो-रिफ़ंड |
| क़तार/कोटा | — | रन-क़तार, डिस्क कोटा |
| लोकल GPU मॉडल | फ़र्स्ट-क्लास (`pip install pipeline[desktop]`) | वैकल्पिक |
| इंस्टॉल | `pip install pipeline[desktop]` → `pipeline ui` | बेस deps + `edition: web`, `hosted_mode: true` |

संस्करण `PIPELINE_EDITION` → `ui_settings.yaml` → डिफ़ॉल्ट **desktop** क्रम से तय होता है; `pipeline doctor` बताता है।

---

## 7. सिस्टम आवश्यकताएँ

**न्यूनतम (क्लाउड/API):** Windows 10/11, Ubuntu 22.04+ या macOS; Python 3.11+; PATH में FFmpeg; 8 GB RAM; 5 GB डिस्क।
**अनुशंसित (लोकल):** RTX 3060+ (8+ GB VRAM, CUDA 12.1+); 16 GB+ RAM; 30 GB SSD।

---

## 8. इंस्टॉलेशन

```bash
git clone https://github.com/sursinges/AI-Video-Content-Factory.git
cd AI-Video-Content-Factory
ffmpeg -version   # न हो तो: winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -e pipeline
```

---

## 9. पहला रन

```bash
python -m core.cli doctor
python -m core.cli run examples/manifest_tech_explainer.yaml --dry-run
python -m core.cli status
python -m core.cli ui --port 8765   # http://localhost:8765 खोलें
```

---

## 10. कॉन्फ़िगरेशन और BYOK

```bash
cp config/ui_settings.example.yaml config/ui_settings.yaml
```

कीज़ `pipeline/.env` में (git से बाहर): `OPENROUTER_API_KEY`, वैकल्पिक `SMALLEST_AI_API_KEY`, `JAMENDO_CLIENT_ID`, `FREESOUND_TOKEN`।

डिफ़ॉल्ट [`pipeline/config/providers.yaml`](pipeline/config/providers.yaml) में: `llm: openrouter`, `tts: smallest_ai` (या silero/chatterbox/voice_studio), `image: local_sd`, `music: ambient_synth`, `publish: mock_publish`।

---

## 11. आर्टिफैक्ट और रिज़्यूम

सब कुछ `pipeline/runs/<run_id>/` में: `script/script.json`, `audio/episode.wav` + `speechplan.json`, `subtitles/subtitles.srt` (+शब्द-JSON), `visual/world.json` + `scenes.json` + `assets/`, `video/episode.mp4` + `timecodes.txt` + `effects_report.json`, `metadata/metadata.json` + `thumbnail.png`।

विफलता पर: `python -m core.cli resume ep-0001` — पूर्ण स्टेज छोड़कर ठीक विफलता-बिंदु से आगे।

---

## 12. सामान्य समस्याएँ

| लक्षण | कारण | समाधान |
|---|---|---|
| `FFmpeg binary not found` | FFmpeg PATH में नहीं | FFmpeg इंस्टॉल करें, टर्मिनल पुनः खोलें। |
| `CUDA out of memory` | SD की VRAM कम | रिज़ॉल्यूशन घटाएँ (`image_size: [768, 432]`) या बाहरी इमेज प्रोवाइडर। |
| `HTTP 429` | प्रोवाइडर कोटा | राउटर दोबारा कोशिश करता है या `fallbacks:` पर जाता है। |
| टेस्ट में `NameError` | pipeline Python path में नहीं | रिपो रूट से `pytest` चलाएँ। |

---

## 13. स्थिति और रोडमैप

- [x] कोर पाइपलाइन M1–M4; मेटाडेटा (S5); Web Studio; doctor; सार्वभौमिक फ़ॉर्मेट।
- [x] सीन-वार image→video (Kling/fal_video; लाइव हेतु `FAL_KEY`)।
- [x] क्लाउड पैकेजिंग: Dockerfile + systemd/Caddy इंस्टॉलर।
- [ ] बैच सीरीज़ प्रोडक्शन।

---

## 14. दस्तावेज़

[PROJECT_STRUCTURE](pipeline/docs/PROJECT_STRUCTURE.md) · [EDITIONS](pipeline/docs/EDITIONS.md) · [RECIPES](pipeline/docs/RECIPES.md) · [VOICE_GUIDE](pipeline/docs/VOICE_GUIDE.md) · [COMMUNITY_PLUGINS](pipeline/docs/COMMUNITY_PLUGINS.md) · [ASSET_RULES](pipeline/config/ASSET_RULES.md)

---

## 15. लाइसेंस

**MIT** ([LICENSE](LICENSE) देखें)। तीसरे पक्ष के मॉडल जोड़ने वाले कंपोनेंट (Silero, Coqui XTTS, Stable Diffusion) अपने-अपने अपस्ट्रीम लाइसेंस के अधीन हैं।
