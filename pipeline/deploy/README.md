# Server Deployment Guide (Ubuntu 22.04+)

This guide explains how to deploy the platform on a Linux server.

Minimum server specs: 2–4 vCPU, 4–8 GB RAM, 50+ GB SSD.
On headless servers, the conveyor operates via **cloud API providers** (OpenAI-compatible LLM, cloud TTS, cloud image generation). Local GPU engines (Chatterbox, local SD) require an NVIDIA GPU instance with CUDA drivers.

---

## Quick Start

```bash
PIPELINE_DOMAIN=video.example.com sudo -E bash deploy/install.sh /opt/pipeline
```

The installer configures:
1. Python 3.11+, FFmpeg, and Caddy reverse proxy.
2. Virtual environment and dependencies.
3. Systemd service (`pipeline.service`) with auto-restart.
4. Automatic HTTPS certificate provisioning via Caddy.

---

## Post-Installation Setup

1. Configure `config/ui_settings.yaml`:
   ```yaml
   hosted_mode: true
   registration_open: true
   max_concurrent_runs: 2
   max_tenant_disk_mb: 2048
   ```
2. The first user to register automatically receives **Admin** privileges.
3. Automated backups:
   ```bash
   python3 tools/host_backup.py --keep 30 --remote rclone_remote:backups
   ```
4. Health check endpoint for uptime monitors:
   ```
   GET /api/health
   ```
