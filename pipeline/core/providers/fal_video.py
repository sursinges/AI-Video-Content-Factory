"""fal.ai image->video adapter (GAP-01 scaffold, BYOK).

Turns a scene image into a short moving clip via the fal.ai queue API
(Kling/Seedance-class models; ~$0.2-1 per clip — the owner decides which
scenes are worth it). Key: fal.ai -> .env FAL_KEY (api_key_ref FAL_KEY).
Model id in cfg.model, default kling v1.6 standard image-to-video.

Payload: {image_path (or image_url), prompt, duration_sec, out_path}
Returns: {video_path, duration_sec, model}
NOTE: wired as a provider + catalog entry only; m3/m4 assembly integration
(hero-scene clips) happens when the owner adds a key and decides the budget.
"""

import time
from pathlib import Path

from core.providers.router import Provider, ProviderError

QUEUE = "https://queue.fal.run"


class FalVideoProvider(Provider):
    adapter = "fal_video"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("fal_video: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        key = self.secret()
        if not key:
            raise ProviderError(
                "fal_video: нет ключа — fal.ai, ключ в .env как FAL_KEY "
                "(api_key_ref: FAL_KEY в providers.yaml). Цена ~$0.2-1 за клип.")
        import httpx

        model = (self.cfg.get("model") or "fal-ai/kling-video/v1.6/standard/image-to-video").strip("/")
        image_url = payload.get("image_url")
        if not image_url:
            img = payload.get("image_path") or ""
            if img and Path(img).exists():
                # fal requires a URL; upload the local file to their storage
                image_url = self._upload(img, key)
            else:
                raise ProviderError("fal_video: нужен image_path (существующий файл) или image_url")
        dur = int(payload.get("duration_sec", 5))
        body = {"prompt": payload.get("prompt", ""), "image_url": image_url,
                "duration": dur if dur in (5, 10) else 5}
        try:
            with httpx.Client(timeout=60) as client:
                r = client.post(f"{QUEUE}/{model}", headers=self._auth(key), json=body)
                r.raise_for_status()
                job = r.json()
                status_url, resp_url = job.get("status_url"), job.get("response_url")
                if not status_url or not resp_url:
                    raise ProviderError(f"fal_video: unexpected queue response: {list(job)}")
                for _ in range(120):  # ~10 min max
                    time.sleep(5)
                    s = client.get(status_url, headers=self._auth(key))
                    s.raise_for_status()
                    if s.json().get("status") != "IN_QUEUE":
                        break
                rr = client.get(resp_url, headers=self._auth(key))
                rr.raise_for_status()
                video_url = ((rr.json() or {}).get("video") or {}).get("url")
                if not video_url:
                    raise ProviderError(f"fal_video: в ответе нет video.url: {str(rr.json())[:200]}")
                dl = client.get(video_url, timeout=300, follow_redirects=True)
                dl.raise_for_status()
                Path(out).write_bytes(dl.content)
                return {"video_path": str(out), "duration_sec": dur, "model": model}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"fal_video: {e}") from e

    @staticmethod
    def _auth(key: str) -> dict:
        return {"Authorization": f"Key {key}"}

    def _upload(self, path: str, key: str) -> str:
        """Initiate a fal storage upload for a local file (3-step flow)."""
        import httpx

        with httpx.Client(timeout=120) as client:
            r = client.post("https://rest.alpha.fal.ai/storage/upload/initiate",
                            headers=self._auth(key),
                            json={"content_type": "image/png", "file_name": Path(path).name})
            r.raise_for_status()
            info = r.json()
            file_url = info.get("file_url")
            put_url = info.get("url")
            if not file_url or not put_url:
                raise ProviderError(f"fal_video: upload initiate failed: {str(info)[:200]}")
            data = Path(path).read_bytes()
            pr = client.put(put_url, content=data,
                            headers={"Content-Type": "image/png"})
            pr.raise_for_status()
            return file_url
