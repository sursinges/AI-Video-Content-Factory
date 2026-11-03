#!/usr/bin/env bash
# Web (Cloud) edition installer — Ubuntu 22.04+/24.04 (CPU host; GPU optional)
# Usage:  sudo PIPELINE_DOMAIN=video.example.com bash deploy/install.sh [ /opt/pipeline ]
set -euo pipefail

TARGET="${1:-/opt/pipeline}"
APP_USER="${SUDO_USER:-$USER}"

echo "==> Packages (ffmpeg, python, caddy repo)"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip ffmpeg git curl debian-keyring debian-archive-keyring apt-transport-https

# The pipeline needs Python >= 3.11 (Ubuntu 22.04 ships 3.10)
PY=python3
if ! python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "==> Python >= 3.11 required — installing python3.11 (deadsnakes)"
  apt-get install -y -qq software-properties-common
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -qq
  apt-get install -y -qq python3.11 python3.11-venv
  PY=python3.11
fi

if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y caddy
fi

echo "==> Code -> $TARGET"
mkdir -p "$TARGET"
if [ -d "$TARGET/.git" ]; then
  git -C "$TARGET" pull --ff-only
else
  git clone https://github.com/sursinges/AI-Video-Content-Factory.git "$TARGET"
fi
chown -R "$APP_USER":"$APP_USER" "$TARGET"
cd "$TARGET"

echo "==> Python venv + dependencies ($PY)"
"$PY" -m venv .venv
./.venv/bin/pip install --upgrade pip wheel
./.venv/bin/pip install -e ./pipeline
# The package lives in pipeline/ (root pyproject is pytest config only).
# Local engines (TTS/images/whisper) are NOT installed on the CPU host by
# default — episodes run on cloud providers or customer workers. For a GPU
# host: ./.venv/bin/pip install -e "pipeline[desktop]".

echo "==> Config seed (Web edition; local file, not committed)"
mkdir -p config data
if [ ! -f config/ui_settings.yaml ]; then
  cat > config/ui_settings.yaml <<'YAML'
edition: web
hosted_mode: false        # flip to true (with registration_open) to arm the sign-in gate
registration_open: false
max_concurrent_runs: 1
workers_enabled: false    # true -> route launches to Hybrid Workers (RFC_HYBRID_WORKERS.md)
YAML
  chown "$APP_USER":"$APP_USER" config/ui_settings.yaml
fi

echo "==> systemd service"
sed "s|__TARGET__|$TARGET|g; s|__USER__|$APP_USER|g" deploy/pipeline.service > /etc/systemd/system/pipeline.service
systemctl daemon-reload
systemctl enable --now pipeline

echo "==> Caddy (auto-HTTPS)"
if [ -n "${PIPELINE_DOMAIN:-}" ]; then
  sed "s|__DOMAIN__|$PIPELINE_DOMAIN|g" deploy/Caddyfile > /etc/caddy/Caddyfile
  systemctl restart caddy
  echo "    https://$PIPELINE_DOMAIN  (Caddy will issue SSL certificate automatically)"
else
  echo "    PIPELINE_DOMAIN not set — Caddy skipped. Specify: PIPELINE_DOMAIN=video.example.com bash deploy/install.sh"
fi

echo "==> Done. Health check:  curl http://127.0.0.1:8765/api/health"
echo "    Edition check:     curl http://127.0.0.1:8765/api/edition"
echo "    Next steps: config/ui_settings.yaml -> hosted_mode: true, registration_open: true"
echo "    Optional: WORKER_TOKEN=<secret> in pipeline/.env to enable Hybrid Workers"
