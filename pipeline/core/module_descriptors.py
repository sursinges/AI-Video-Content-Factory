"""Module descriptors — a machine-readable registry of the pipeline stages.
Used by stage-2 tooling (visual builders, marketplace cards, docs) instead of hard-coding stages.

Each descriptor: stable id, human name, which provider type powers it, the
contract artifacts it consumes/produces (relative to run_dir). The JSON
contracts themselves live in core/contracts."""

from typing import Any

DESCRIPTORS: list[dict[str, Any]] = [
    {
        "id": "m1_script",
        "name": "Script",
        "provider_type": "llm",
        "inputs": ["episode.manifest.json"],
        "outputs": ["script/script.json", "script/subtitles.srt"],
        "description": "Skeleton generation -> chunks -> drama critique -> fact-check; language and tone from profile.",
    },
    {
        "id": "m2_audio",
        "name": "Audio",
        "provider_type": "tts",
        "inputs": ["script/script.json"],
        "outputs": ["audio/audio_result.json", "audio/voice.wav", "subtitles/subtitles.srt"],
        "description": "Chunked TTS synthesis with emotion tags; Whisper alignment for timestamps and subtitles.",
    },
    {
        "id": "m3_visual",
        "name": "Visual",
        "provider_type": "image",
        "inputs": ["audio/audio_result.json"],
        "outputs": ["visual/scenes.json", "visual/frames/"],
        "description": "Timecoded scene direction, frame generation matching visual preset, visual critique.",
    },
    {
        "id": "m4_assembly",
        "name": "Assembly",
        "provider_type": "music",
        "inputs": ["visual/scenes.json", "audio/voice.wav"],
        "outputs": ["video/episode.mp4", "video/assembly_result.json"],
        "description": "Frame animation with Ken Burns FX -> crossfades -> background audio mix -> subtitle burn-in.",
    },
    {
        "id": "m5_metadata",
        "name": "Metadata",
        "provider_type": "llm",
        "inputs": ["video/episode.mp4"],
        "outputs": ["metadata/metadata.json", "metadata/timecodes.txt"],
        "description": "SEO titles, descriptions, hashtags, chapter timecodes, and cover thumbnail.",
    },
    {
        "id": "m6_publish",
        "name": "Publish",
        "provider_type": "publish",
        "inputs": ["metadata/metadata.json", "video/episode.mp4"],
        "outputs": ["publish_result.json"],
        "description": "Multi-channel publishing, OAuth credential rotation, scheduling, and upload automation.",
    },
]
