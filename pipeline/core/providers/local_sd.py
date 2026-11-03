"""Local Stable Diffusion image adapter (owner decision 2026-09-12: no image
API key — generate locally on the RTX 3070 Ti). fp16 pipeline, lazily loaded
once per process; writes payload["out_path"]."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

_pipe_cache: dict = {}


class LocalSDProvider(Provider):
    adapter = "local_sd"

    def _pipeline(self, img2img: bool = False):
        import torch

        key = self.cfg.get("model", "stable-diffusion-v1-5/stable-diffusion-v1-5")
        cache_key = f"{key}::{img2img}"
        if cache_key not in _pipe_cache:
            if img2img:
                from diffusers import StableDiffusionImg2ImgPipeline

                pipe_cls, kwargs = StableDiffusionImg2ImgPipeline, {}
            else:
                from diffusers import StableDiffusionPipeline

                pipe_cls, kwargs = StableDiffusionPipeline, {}
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            pipe = pipe_cls.from_pretrained(
                key, torch_dtype=dtype, safety_checker=None,
                requires_safety_checker=False, **kwargs)
            pipe = pipe.to(device)
            if device == "cuda":
                pipe.enable_attention_slicing()  # 8 GB VRAM budget
            _pipe_cache[cache_key] = pipe
        return _pipe_cache[cache_key]

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("local_sd: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image
            import torch

            init = payload.get("init_image")
            if init and Path(init).exists():
                pipe = self._pipeline(img2img=True)
                gen = torch.Generator(device=pipe.device).manual_seed(int(payload.get("seed", 0)))
                init_img = Image.open(init).convert("RGB")
                image = pipe(
                    prompt=payload["prompt"],
                    negative_prompt=payload.get("negative") or None,
                    image=init_img,
                    strength=float(self.cfg.get("ref_strength", 0.55)),
                    num_inference_steps=int(self.cfg.get("steps", 25)),
                    guidance_scale=float(self.cfg.get("guidance", 7.0)),
                    generator=gen,
                ).images[0]
            else:
                pipe = self._pipeline()
                gen = torch.Generator(device=pipe.device).manual_seed(int(payload.get("seed", 0)))
                w, h = payload.get("width", 1024), payload.get("height", 576)
                w, h = w - w % 64, h - h % 64  # SD needs multiples of 64
                image = pipe(
                    prompt=payload["prompt"],
                    negative_prompt=payload.get("negative") or None,
                    width=w, height=h,
                    num_inference_steps=int(self.cfg.get("steps", 25)),
                    guidance_scale=float(self.cfg.get("guidance", 7.0)),
                    generator=gen,
                ).images[0]
            image.save(out)
            return {"image_path": str(out)}
        except Exception as e:  # noqa: BLE001 — surface as provider error
            raise ProviderError(f"local_sd: {e}") from e
