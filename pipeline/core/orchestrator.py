"""Orchestrator: fixed step order, checkpoints, resume, dry-run (architecture §3.1)."""

import json
import time
from pathlib import Path


import yaml

from core.contracts import EpisodeManifest
from core.i18n import tr
from core.providers.router import Router
from core import tenants
from core.state import LibraryDB, StateDB
from modules.base import RunContext

STEPS = ["m1_script", "m2_audio", "m3_visual", "m4_assembly", "m5_metadata", "m6_publish"]


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_modules():
    from modules.m1_script.runner import M1Script
    from modules.m2_audio.runner import M2Audio
    from modules.m3_visual.runner import M3Visual
    from modules.m4_assembly.runner import M4Assembly
    from modules.m5_metadata.runner import M5Metadata
    from modules.m6_publish.runner import M6Publish

    return {m.name: m() for m in (M1Script, M2Audio, M3Visual, M4Assembly, M5Metadata, M6Publish)}


class Orchestrator:
    def __init__(self, workspace: str | Path, lang: str = "ru", on_event=None):
        from core.secrets import load_env

        self.workspace = Path(workspace)
        load_env(self.workspace / ".env")  # API keys from .env (gitignored)
        # Multi-tenant (P5): runs/ and data/ resolve under the tenant data root
        # (PIPELINE_DATA_ROOT env, set by the UI server for tenant subprocesses);
        # without it this is the global single-owner workspace.
        from core.tenants import resolve_data_root
        self.data_root = resolve_data_root(self.workspace)
        if self.data_root != self.workspace:
            load_env(self.data_root / ".env")  # tenant BYOK keys override host ones
        self.lang = lang
        self.on_event = on_event or (lambda msg: None)
        self.state = StateDB(self.data_root / "data" / "state.db")
        self.library = LibraryDB(self.data_root / "data" / "library.db")
        self._tenants = tenants
        self._modules = None

    def close(self):
        self.state.close()
        self.library.close()

    @property
    def modules(self):
        if self._modules is None:
            self._modules = _load_modules()
        return self._modules

    # -- entry points ----------------------------------------------------------
    def _preflight_check(self, manifest: EpisodeManifest, dry_run: bool, steps: list[str]) -> None:
        import shutil

        # 1. FFmpeg validation for audio/video stages
        if ("m2_audio" in steps or "m4_assembly" in steps) and not shutil.which("ffmpeg"):
            raise RuntimeError(
                "Pre-flight validation failed: FFmpeg binary not found on system PATH. "
                "FFmpeg is required for audio synthesis, loudnorm, and video assembly. "
                "Installation guide: https://ffmpeg.org/download.html (or 'winget install Gyan.FFmpeg' on Windows)."
            )

        # 2. Channel profile validation
        profile_path = tenants.resolve_config(self.workspace, manifest.profile)
        if not profile_path.exists():
            raise FileNotFoundError(
                f"Pre-flight validation failed: Profile '{manifest.profile}' not found at {profile_path}."
            )

    def run(self, manifest_path: str | Path, until: str | None = None,
            dry_run: bool = False, resume: bool = False) -> str:
        manifest_path = Path(manifest_path)
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = EpisodeManifest(**raw)

        steps = STEPS[: STEPS.index(until) + 1] if until else STEPS
        self._preflight_check(manifest, dry_run, steps)

        run_dir = self.data_root / "runs" / manifest.run_id
        providers_cfg = yaml.safe_load(
            tenants.resolve_config(self.workspace, "config/providers.yaml").read_text(encoding="utf-8")
        )
        if dry_run:
            providers_cfg = dict(providers_cfg)
            providers_cfg["defaults"] = {
                t: ("mock" if t == "llm" else f"mock_{t}")
                for t in ("llm", "tts", "stt", "image", "music", "search", "publish")
            }

        # per-episode provider selection (product vision: visual choice per step)
        pov = (manifest.overrides or {}).get("provider_overrides")
        if pov:
            providers_cfg = dict(providers_cfg)
            providers_cfg["defaults"] = {**(providers_cfg.get("defaults") or {}), **pov}
        providers_cfg["_model_overrides"] = (manifest.overrides or {}).get("model_overrides") or {}
        router = Router(providers_cfg, self.state, manifest.run_id, run_dir, self.lang)
        router.on_event = self.on_event
        profile_path = tenants.resolve_config(self.workspace, manifest.profile)
        profile = yaml.safe_load(
            profile_path.read_text(encoding="utf-8")
        ) if profile_path.exists() else {}
        # format presets: merge format defaults under profile (profile wins)
        fmt_file = tenants.resolve_config(self.workspace, "config/formats.yaml")
        if fmt_file.exists():
            fmts = yaml.safe_load(fmt_file.read_text(encoding="utf-8")) or {}
            fmt = fmts.get(manifest.format)
            if isinstance(fmt, dict):
                vp = fmt.pop("visual_preset", None)
                if vp:
                    fmt.setdefault("visual", {})["preset"] = vp
                if "music_mood" in fmt:
                    fmt.setdefault("audio_mix", {})["music_mood"] = fmt.pop("music_mood")
                profile = _deep_merge(fmt, profile)
        profile = _deep_merge(profile, manifest.overrides)

        if not resume:
            self.state.create_run(manifest.run_id, manifest.model_dump())
            mode = "dry-run" if dry_run else "full"
            self.on_event(tr(self.lang, "run_started", run_id=manifest.run_id, mode=mode))

        self.library.upsert_episode(manifest.run_id, manifest.channel_id, manifest.topic)
        ctx = RunContext(
            manifest=manifest, run_dir=run_dir, workspace=self.workspace, profile=profile,
            router=router, state=self.state, library=self.library, dry_run=dry_run,
            data_root=self.data_root,
        )

        steps = STEPS[: STEPS.index(until) + 1] if until else STEPS
        self.state.set_run_status(manifest.run_id, "running")
        timing_file = ctx.run_dir / "timing_report.json"
        timing_data = {}
        if timing_file.exists():
            try:
                timing_data = json.loads(timing_file.read_text(encoding="utf-8"))
            except Exception:
                timing_data = {}
        try:
            for step in steps:
                if self.state.is_step_done(manifest.run_id, step):
                    self.on_event(tr(self.lang, "step_skip", step=step))
                    continue
                try:
                    self.state.set_step(manifest.run_id, step, "running")
                    t0 = time.time()
                    artifacts = self.modules[step].run(ctx)
                    step_dur = round(time.time() - t0, 2)
                    primary = ""
                    for rel, model in artifacts:
                        path = ctx.artifact_path(rel)
                        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
                        primary = primary or str(path)
                    self.state.set_step(manifest.run_id, step, "done", primary)
                    timing_data[step] = {"duration_sec": step_dur, "status": "done"}
                    try:
                        ctx.run_dir.mkdir(parents=True, exist_ok=True)
                        timing_file.write_text(json.dumps(timing_data, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    self.on_event(tr(self.lang, "step_done", step=step, artifact=primary))
                except Exception as e:  # noqa: BLE001 — any step failure stops the run
                    self.state.set_step(manifest.run_id, step, "failed", error=str(e))
                    self.state.set_run_status(manifest.run_id, "failed")
                    # billing (P5-02): a failed run returns the credit it spent
                    if self.data_root != self.workspace:
                        tenants.refund_credit(self.workspace, self.data_root.name)
                    self.on_event(tr(self.lang, "step_fail", step=step, error=e))
                    raise
            self.state.set_run_status(manifest.run_id, "done")
            self.on_event(tr(self.lang, "run_finished", run_id=manifest.run_id))
        finally:
            router.run_dir.mkdir(parents=True, exist_ok=True)

        return manifest.run_id

    def resume(self, run_id: str, until: str | None = None, dry_run: bool = False,
               from_step: str | None = None) -> str:
        row = self.state.get_run(run_id)
        if not row:
            raise ValueError(f"run '{run_id}' not found")
        if from_step:
            if from_step not in STEPS:
                raise ValueError(f"unknown step '{from_step}'. Must be one of: {', '.join(STEPS)}")
            self.state.reset_steps_from(run_id, from_step, STEPS)
        raw = json.loads(row["manifest"])
        tmp = self.data_root / "runs" / run_id / "episode.manifest.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        return self.run(tmp, until=until, dry_run=dry_run, resume=True)

    def status(self, run_id: str | None = None) -> list[dict]:
        if run_id:
            runs = [self.state.get_run(run_id)] if self.state.get_run(run_id) else []
        else:
            runs = self.state.list_runs()
        out = []
        for r in runs:
            steps = self.state.conn.execute(
                "SELECT step, status, artifact, error FROM steps WHERE run_id=?", (r["run_id"],)
            ).fetchall()
            out.append({"run_id": r["run_id"], "status": r["status"],
                        "steps": {s["step"]: {"status": s["status"], "artifact": s["artifact"],
                                              "error": s["error"]} for s in steps}})
        return out
