"""System diagnostics and health check for the AI Video Content Factory."""

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def check_python() -> dict[str, Any]:
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    ok = ver >= (3, 11)
    return {
        "name": "Python Environment",
        "status": "ok" if ok else "error",
        "version": ver_str,
        "detail": sys.executable,
        "message": "Python >= 3.11 required." if not ok else "Compatible version.",
    }


def check_ffmpeg() -> dict[str, Any]:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        return {
            "name": "FFmpeg & FFprobe",
            "status": "error",
            "version": None,
            "detail": f"ffmpeg: {'found' if ffmpeg_path else 'missing'}, ffprobe: {'found' if ffprobe_path else 'missing'}",
            "message": "FFmpeg is required for video/audio assembly. Install via winget (Windows): winget install Gyan.FFmpeg, or brew/apt.",
        }

    try:
        proc = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, timeout=5)
        first_line = proc.stdout.splitlines()[0] if proc.stdout else "Unknown version"
        version_part = first_line.split("Copyright")[0].strip()
        return {
            "name": "FFmpeg & FFprobe",
            "status": "ok",
            "version": version_part,
            "detail": str(ffmpeg_path),
            "message": "FFmpeg is installed and accessible.",
        }
    except Exception as e:
        return {
            "name": "FFmpeg & FFprobe",
            "status": "error",
            "version": None,
            "detail": str(e),
            "message": "FFmpeg command failed to execute.",
        }


def check_cuda_gpu() -> dict[str, Any]:
    try:
        import torch  # type: ignore

        has_cuda = torch.cuda.is_available()
        if has_cuda:
            device_name = torch.cuda.get_device_name(0)
            mem_bytes = torch.cuda.get_device_properties(0).total_memory
            mem_gb = round(mem_bytes / (1024**3), 2)
            return {
                "name": "Hardware Acceleration (CUDA)",
                "status": "ok",
                "version": f"Torch {torch.__version__}",
                "detail": f"{device_name} ({mem_gb} GB VRAM)",
                "message": f"GPU acceleration active. Suitable for local Stable Diffusion & TTS models.",
            }
        return {
            "name": "Hardware Acceleration (CUDA)",
            "status": "warning",
            "version": f"Torch {torch.__version__}",
            "detail": "CPU-only mode",
            "message": "No CUDA GPU detected. Local SD/F5-TTS will be slow or disabled; external API providers recommended.",
        }
    except ImportError:
        return {
            "name": "Hardware Acceleration (CUDA)",
            "status": "info",
            "version": None,
            "detail": "PyTorch not installed",
            "message": "PyTorch is optional if using external API providers exclusively.",
        }
    except Exception as e:
        return {
            "name": "Hardware Acceleration (CUDA)",
            "status": "warning",
            "version": None,
            "detail": str(e),
            "message": "Unable to probe GPU status.",
        }


def check_disk_space(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        free_gb = round(usage.free / (1024**3), 2)
        total_gb = round(usage.total / (1024**3), 2)
        status = "ok" if free_gb >= 10.0 else ("warning" if free_gb >= 3.0 else "error")
        return {
            "name": "Storage Space",
            "status": status,
            "version": None,
            "detail": f"{free_gb} GB free of {total_gb} GB total",
            "message": "Sufficient disk space." if status == "ok" else "Low disk space (<10 GB recommended for rendering).",
        }
    except Exception as e:
        return {
            "name": "Storage Space",
            "status": "warning",
            "version": None,
            "detail": str(e),
            "message": "Could not inspect disk usage.",
        }


def check_core_packages() -> dict[str, Any]:
    required = ["pydantic", "typer", "httpx", "yaml", "fastapi", "uvicorn"]
    missing = []
    versions = {}
    for pkg in required:
        try:
            mod = importlib.import_module(pkg)
            versions[pkg] = getattr(mod, "__version__", "installed")
        except ImportError:
            missing.append(pkg)

    if missing:
        return {
            "name": "Core Python Packages",
            "status": "error",
            "version": None,
            "detail": f"Missing: {', '.join(missing)}",
            "message": "Install dependencies with: pip install -e pipeline",
        }
    return {
        "name": "Core Python Packages",
        "status": "ok",
        "version": None,
        "detail": ", ".join(f"{k} {v}" for k, v in versions.items()),
        "message": "All essential packages are installed.",
    }


def check_configs(workspace: Path) -> list[dict[str, Any]]:
    results = []
    configs = [
        ("config/providers.yaml", "Providers Configuration", True),
        ("config/channel.profile.yaml", "Default Channel Profile", True),
        ("config/formats.yaml", "Video Formats", True),
        ("config/visual_presets.yaml", "Visual Presets", False),
    ]

    for rel_path, title, required in configs:
        target = workspace / rel_path
        if not target.exists():
            results.append({
                "name": title,
                "status": "error" if required else "warning",
                "detail": rel_path,
                "message": f"File '{rel_path}' not found.",
            })
            continue

        try:
            data = yaml.safe_load(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a YAML dictionary at root.")
            results.append({
                "name": title,
                "status": "ok",
                "detail": f"{len(data)} items loaded from {rel_path}",
                "message": "Valid configuration file.",
            })
        except Exception as e:
            results.append({
                "name": title,
                "status": "error",
                "detail": rel_path,
                "message": f"YAML syntax error: {e}",
            })

    return results


def check_api_keys(workspace: Path) -> dict[str, Any]:
    from core.secrets import load_env
    load_env(workspace / ".env")

    providers_file = workspace / "config" / "providers.yaml"
    if not providers_file.exists():
        return {
            "name": "Provider API Keys (BYOK)",
            "status": "warning",
            "detail": "providers.yaml missing",
            "message": "Cannot inspect providers.",
        }

    try:
        cfg = yaml.safe_load(providers_file.read_text(encoding="utf-8")) or {}
        providers = cfg.get("providers", {})
        defaults = cfg.get("defaults", {})

        key_status = {}
        for pid, pdata in providers.items():
            ptype = pdata.get("type", "unknown")
            ref = pdata.get("api_key_ref")
            adapter = pdata.get("adapter", "mock")
            if ref:
                is_set = bool(os.environ.get(ref))
                is_default = defaults.get(ptype) == pid
                key_status[pid] = {
                    "type": ptype,
                    "env_var": ref,
                    "is_set": is_set,
                    "is_default": is_default,
                    "adapter": adapter,
                }

        configured_count = sum(1 for v in key_status.values() if v["is_set"])
        total_api_count = len(key_status)

        return {
            "name": "Provider API Keys (BYOK)",
            "status": "ok" if configured_count > 0 else "info",
            "detail": f"{configured_count}/{total_api_count} API keys set in .env",
            "keys": key_status,
            "message": "All default providers configured." if configured_count > 0 else "No API keys configured; local and mock providers will be used.",
        }
    except Exception as e:
        return {
            "name": "Provider API Keys (BYOK)",
            "status": "warning",
            "detail": str(e),
            "message": "Failed to parse provider keys.",
        }


def run_diagnostics(workspace: Path) -> dict[str, Any]:
    checks = [
        check_python(),
        check_ffmpeg(),
        check_cuda_gpu(),
        check_disk_space(workspace),
        check_core_packages(),
    ]
    checks.extend(check_configs(workspace))
    checks.append(check_api_keys(workspace))

    has_error = any(c["status"] == "error" for c in checks)
    has_warning = any(c["status"] == "warning" for c in checks)

    overall = "error" if has_error else ("warning" if has_warning else "ok")
    return {
        "overall": overall,
        "workspace": str(workspace),
        "checks": checks,
    }


def print_diagnostics_report(report: dict[str, Any], lang: str = "en") -> None:
    symbols = {
        "ok": "[✓]",
        "warning": "[!]",
        "error": "[✗]",
        "info": "[i]",
    }

    print("\n=== AI Video Content Factory — System Diagnostics ===")
    print(f"Workspace: {report['workspace']}\n")

    for item in report["checks"]:
        sym = symbols.get(item["status"], "[?]")
        name = item["name"]
        detail = f" — {item['detail']}" if item.get("detail") else ""
        msg = f"   └─ {item['message']}" if item.get("message") else ""

        print(f"{sym} {name}{detail}")
        if msg:
            print(msg)

    print("\n-----------------------------------------------------")
    if report["overall"] == "ok":
        print("Status: ALL CLEAR. The system is ready to produce videos.")
    elif report["overall"] == "warning":
        print("Status: OPERATIONAL WITH WARNINGS. Check recommendations above.")
    else:
        print("Status: CRITICAL ISSUES DETECTED. Resolve the errors [✗] before running.")
    print("-----------------------------------------------------\n")
