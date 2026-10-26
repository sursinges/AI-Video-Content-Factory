# Pipeline Engine

Modular pipeline engine that turns an idea or topic into a ready-to-publish video:
**script → audio → visual → assembly → metadata → publish**.

- Architecture & Structure: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- Custom Providers & Recipes: [docs/RECIPES.md](docs/RECIPES.md)
- Voice & TTS Setup: [docs/VOICE_GUIDE.md](docs/VOICE_GUIDE.md)
- Community Plugins: [docs/COMMUNITY_PLUGINS.md](docs/COMMUNITY_PLUGINS.md)

## Quick Start (Mock mode — no API keys needed)

```bash
# Activate virtual environment
.venv/Scripts/activate            # Windows (Git Bash: source .venv/Scripts/activate)

# Verify environment
python -m core.cli doctor

# Run dry run
python -m core.cli run config/episode.template.yaml --dry-run
python -m core.cli status
```

Real providers are configured in `config/providers.yaml` + secrets in `.env` (gitignored).

Episode overrides go straight into the manifest (`overrides:` merges over the channel profile), e.g. custom chunk sizes:

```yaml
overrides:
  script:
    chunk_chars: [300, 600]
```
