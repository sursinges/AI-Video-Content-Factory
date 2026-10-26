# Project Structure & Architecture Guide

This document describes the directory structure, component responsibilities, and dependency rules of **AI-Video-Content-Factory**.

---

## 1. Directory Layout

```
AI-Video-Content-Factory/
├── README.md               # Main public documentation & quick start
├── LICENSE                 # MIT License with model attribution notes
├── pyproject.toml          # Root test and package configuration
├── examples/               # Production-ready episode manifests for various formats
│   ├── manifest_short_vertical.yaml     # 9:16 Shorts / Reels / TikTok preset
│   ├── manifest_tech_explainer.yaml     # 16:9 Tech & Product review preset
│   └── manifest_educational_story.yaml  # 16:9 Long-form narrative story preset
└── pipeline/
    ├── config/             # Formats, providers, channel profiles, and visual presets
    ├── core/               # Conveyor engine, Pydantic contracts, state DB, router
    │   ├── contracts/      # Deterministic JSON schemas for all 6 modules
    │   ├── providers/      # Unified router and provider adapters
    │   ├── cli.py          # Command line interface (run, status, resume, doctor)
    │   ├── diagnostics.py  # System health checker (Python, FFmpeg, CUDA, disk, BYOK)
    │   ├── orchestrator.py # Linear conveyor executor with resume and preflight
    │   └── state.py        # SQLite runtime state & cache management
    ├── modules/            # 6 isolated pipeline stages
    │   ├── m1_script/      # Skeleton generation, chunking, drama critique, fact check
    │   ├── m2_audio/       # Speech planning, TTS synthesis, Whisper subtitles
    │   ├── m3_visual/      # Visual world context, scene planning, frame generation
    │   ├── m4_assembly/    # FFmpeg montage, Ken Burns, audio normalization, subtitle burn
    │   ├── m5_metadata/    # Title, description, chapter timecodes, thumbnail cover
    │   └── m6_publish/     # Channel publisher with account rotation and scheduling
    ├── motion_templates/   # HTML5 kinetic typography & graphic cards
    ├── prompts/            # Versioned prompt templates with dynamic variables
    ├── tests/              # Automated unit and integration test suite
    └── ui/                 # Web Studio dashboard & REST API server
```

---

## 2. Dependency Guidelines

- **PyTorch & CUDA:**
  For local GPU acceleration (TTS, Stable Diffusion), install PyTorch with CUDA 12.1+:
  ```bash
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
  ```
  Verify via:
  ```bash
  python -c "import torch; print('CUDA Available:', torch.cuda.is_available())"
  ```
- **FFmpeg:**
  FFmpeg 6.0+ is required on system `PATH` for loudnorm audio processing, video scaling, and concatenation.
