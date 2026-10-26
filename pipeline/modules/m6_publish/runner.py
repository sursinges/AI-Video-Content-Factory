"""M6 publish module (S6): picks an account from the pool and uploads via the
publish provider. Real upload needs YouTube OAuth credentials (config/accounts.yaml
+ core/providers/youtube_api.py, wired when the owner creates the Google Cloud
OAuth client); until then the mock provider returns a mock result."""

import json

import yaml

from core.contracts import PublishResult
from modules.base import Artifact, Module, RunContext


class M6Publish(Module):
    name = "m6_publish"

    def _pick_account(self, ctx) -> dict:
        # per-tenant accounts first (hosted users publish to their own channels)
        cfg_path = (ctx.data_root / "config" / "accounts.yaml") \
            if getattr(ctx, "data_root", None) and (ctx.data_root / "config" / "accounts.yaml").exists() \
            else (ctx.workspace / "config" / "accounts.yaml")
        if not cfg_path.exists():
            return {"id": "acc1", "label": "default", "oauth_profile": "acc1", "default": True}
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        accounts = cfg.get("accounts") or []
        rotation = cfg.get("rotation", "manual")
        if rotation == "round_robin" and accounts:
            # deterministic rotation by run count of this channel
            done = ctx.state.conn.execute(
                "SELECT COUNT(*) c FROM steps WHERE run_id LIKE ?", ("%ep-%",)).fetchone()["c"]
            return accounts[done % len(accounts)]
        for acc in accounts:
            if acc.get("default"):
                return acc
        return accounts[0] if accounts else {"id": "acc1", "label": "default",
                                             "oauth_profile": "acc1", "default": True}

    def run(self, ctx: RunContext) -> list[Artifact]:
        acc = self._pick_account(ctx)
        meta = json.loads((ctx.run_dir / "metadata" / "metadata.json").read_text(encoding="utf-8"))
        res = ctx.router.call("publish", {
            "video_path": str(ctx.run_dir / "video" / "episode.mp4"),
            "metadata": meta,
            "account": acc,
            "visibility": ctx.manifest.overrides.get("publish_visibility", "unlisted"),
            "publish_at": ctx.manifest.overrides.get("publish_at"),  # RFC 3339 UTC
        })
        result = PublishResult(
            account_id=acc["id"], video_id=res.get("video_id"),
            visibility=res.get("visibility", "unlisted"),
            uploaded_at=res.get("uploaded_at"), status=res.get("status", "mock"),
        )
        if result.video_id and result.status == "done":
            ctx.library.set_episode_published(ctx.manifest.run_id, result.video_id)
        return [("publish_result.json", result)]
