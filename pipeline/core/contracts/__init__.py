"""Data contracts module-by-module. Single source of truth: techplan §5."""
from core.contracts.manifest import EpisodeManifest
from core.contracts.script import FactCheck, FactCheckClaim, Script, ScriptChunk, Skeleton
from core.contracts.audio import (AudioResult, SpeechPlan, SubLine, Subtitles,
                                  TtsSegment, Word)
from core.contracts.visual import Scene, Scenes, WorldContext
from core.contracts.assembly import AssemblyResult
from core.contracts.metadata import Chapter, Metadata, ThumbnailSpec, YoutubeMeta
from core.contracts.publish import PublishAccount, PublishResult

__all__ = [
    "EpisodeManifest",
    "Script", "ScriptChunk", "FactCheck", "FactCheckClaim", "Skeleton",
    "SpeechPlan", "TtsSegment", "Subtitles", "Word", "SubLine", "AudioResult",
    "WorldContext", "Scene", "Scenes",
    "AssemblyResult",
    "Metadata", "Chapter", "ThumbnailSpec", "YoutubeMeta",
    "PublishAccount", "PublishResult",
]
