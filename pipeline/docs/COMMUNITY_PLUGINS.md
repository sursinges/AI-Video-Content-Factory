# Community Plugins & Extensibility Policy
### Licensing Policy for Public & Open-Source Releases

> This document defines the boundary between what belongs in the core product repository
> and what is delegated to community plugins — ensuring clean licensing, compliance,
> and security for the open core.

---

## 1. Boundary Principle

**Core (Public Repository):**
- Strictly official provider APIs (YouTube Data API v3, OpenAI-compatible endpoints,
  ElevenLabs, Jamendo, Fal.ai, etc.) and local models with permissive licenses
  (MIT/Apache — Silero, Coqui, Chatterbox, Stable Diffusion).
- BYOK (Bring Your Own Key): user-owned keys, zero mediation or quota resale.
- Core License: Source-available license (based on standard fair-code / Sustainable Use models).

**Community Plugins (Independent Repositories, Outside Core):**
- May use specialized techniques (browser sessions, scraping, region proxies) — responsibility
  and compliance rests entirely with the plugin author.
- May be commercial or proprietary — revenue belongs to the community author.
- The core project does NOT bundle or distribute unverified external scraping plugins.
- Plugins integrate through the public provider and module extension interfaces.

## 2. Rationale

- **Platform Compliance:** Embedding scrapers directly into core creates legal and operational risks
  for users and opens exposure to DMCA takedowns and IP blocks. We provide official API adapters
  (e.g., YouTube Data API) as first-class citizens.
- **Clean-Room Engineering:** We do not copy AGPL or restricted codebases; all architecture in
  the core is implemented cleanly under permissive or source-available standards.
- **Monetization & Freedom:** Community authors can monetize their plugins in their own
  repositories without restricting core users. The platform provides discovery and configuration hooks.

## 3. Trend Research: Core vs. Plugins

| Feature | Location | Implementation |
|---|---|---|
| YouTube: Search + Statistics + Velocity | **CORE** (`ui/api_market.py`) | Official YouTube Data API v3 (10,000 units/day quota, key in `.env`) |
| YouTube: Search Suggestions | Plugin | Optional suggestqueries endpoint plugin (read-only) |
| Google Trends (`pytrends`) | Plugin | Community plugin slot |
| TikTok / Instagram Scout | Plugin | Official third-party APIs or author-maintained plugins |
| Outlier Detection (3x-20x baseline) | Core / Plugin | Connected channel analytics (OAuth read-only) |
| News & RSS Scout | Plugin | RSS parser + LLM summarization |

## 4. Architectural Readiness for Plugins

- Provider registry supporting arbitrary OpenAI-compatible endpoints (BYOK).
- Isolated plugin directory slot (`grey_plugins/`) excluded from core git distribution.
- Runtime flags in configuration allowing modules to run in mock or headless modes without optional plugins.

## 5. Public Release Checklist

- [x] Zero hardcoded keys or private tokens in tracked files.
- [x] Independent configuration and plugin isolation.
- [x] Clear licensing terms and BYOK documentation.
- [x] Dependency audit ensuring clean-room permissive baseline.
