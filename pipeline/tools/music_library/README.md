# Music Library: Local Background Track Manager

This module manages royalty-free background music tracks for video assembly.

---

## Usage

1. Download royalty-free audio tracks (e.g. from YouTube Audio Library or Pixabay) into `models/music/`.
2. Name files with their mood keyword for automatic selection:
   - `calm_ambient_01.mp3`
   - `tech_minimal_01.mp3`
   - `upbeat_documentary_01.mp3`

### CLI Commands

```bash
# Rebuild the track index
python tools/music_library/manager.py scan

# Query tracks by mood
python tools/music_library/manager.py pick --mood tech_minimal
```

### Pipeline Integration

The `library_music` adapter (`core/providers/library_music.py`) matches the `music_mood` specified in the episode format or channel profile and selects a suitable background track for M4 Assembly. If the local directory has no matching tracks, the router gracefully falls back to procedural ambient synthesis (`ambient_synth`).
