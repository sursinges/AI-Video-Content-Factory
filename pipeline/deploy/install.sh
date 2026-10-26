#!/usr/bin/env bash
# pipeline host installer — Ubuntu 22.04+ (CPU start; GPU optional)
# Usage:  sudo bash deploy/install.sh [ /opt/pipeline ]
set -euo pipefail

TARGET="${1:-/opt/pipeline}"
APP_USER="${SUDO_USER:-$USER}"

echo "==> Packages (ffmpeg, python, caddy repo)"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip ffmpeg git curl debian-keyring debian-archive-keyring apt-transport-https

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

echo "==> Python venv + dependencies"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip wheel
./.venv/bin/pip install -e .
# local engines (TTS/images/whisper) are NOT installed on the CPU host by
# default — episodes run on cloud providers. GPU server: install them manually.

echo "==> Config seed (copy host defaults on first run)"
mkdir -p config data

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
echo "    Next steps: config/ui_settings.yaml -> hosted_mode: true, registration_open: true"
