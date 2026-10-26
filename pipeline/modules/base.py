"""Shared run context and module interface."""
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from core.contracts import EpisodeManifest
from core.providers.router import Router
from core.state import LibraryDB, StateDB


@dataclass
class RunContext:
    manifest: EpisodeManifest
    run_dir: Path
    workspace: Path
    profile: dict
    router: Router
    state: StateDB
    library: LibraryDB
    dry_run: bool
    data_root: Path | None = None  # tenant data root (P5) — None = global workspace

    def artifact_path(self, rel: str) -> Path:
        p = self.run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


Artifact = tuple[str, BaseModel]  # (relative path, validated model)


class Module:
    """One conveyor step. A module reads only its inputs and writes only its
    outputs (architecture §5) — enforced by the orchestrator's validation."""

    name: str = ""

    def run(self, ctx: RunContext) -> list[Artifact]:
        raise NotImplementedError
