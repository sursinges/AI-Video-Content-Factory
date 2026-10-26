"""Local music library adapter (tools/music_library): picks a track by mood
from the scanned index (owner downloads free YouTube Audio Library tracks
manually — that library has no public API). Falls back to error so the router
can use its fallback chain (mock silence)."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

sys_paths = [str(Path(__file__).resolve().parents[1] / "tools" / "music_library")]


class LibraryMusicProvider(Provider):
    adapter = "library_music"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("library_music: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        folder = self.cfg.get("path", "models/music")

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "music_manager", Path(__file__).resolve().parents[1] / "tools" / "music_library" / "manager.py")
        mgr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mgr)
        if not mgr.INDEX.exists():
            mgr.scan(folder)
        track = mgr.pick(payload.get("mood"))
        if not track or not Path(track).exists():
            raise ProviderError("library_music: каталог пуст — скачай треки из "
                                "YouTube Audio Library в models/music/ и запусти scan")
        import shutil

        shutil.copy(track, out)
        return {"audio_path": str(out)}
