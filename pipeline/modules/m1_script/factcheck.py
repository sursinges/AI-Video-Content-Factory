"""Fact-check (S1-05): claims extraction via LLM, «well-known only» rule,
optional search provider annotates flagged claims. Dry-run → clean pass."""

from core.contracts import FactCheck, FactCheckClaim
from modules.m1_script.prompts import extract_json, render


def factcheck_chunk(ctx, base_vars: dict, chunk_text: str) -> FactCheck:
    if ctx.dry_run:
        return FactCheck(status="pass")

    variables = base_vars | {"chunk_text": chunk_text}
    resp = ctx.router.call("llm", {"prompt": render("factcheck.md", variables), "temperature": 0.1})
    data = extract_json(resp.get("text", ""))
    if not data:
        return FactCheck(status="pass")

    claims = []
    for c in data.get("claims", []):
        if not c.get("text"):
            continue
        claims.append(FactCheckClaim(text=str(c["text"]),
                                     verdict="flagged" if c.get("verdict") == "flagged" else "well-known"))

    flagged = [c for c in claims if c.verdict == "flagged"]
    if flagged:
        _annotate_with_search(ctx, flagged)
    return FactCheck(status="warnings" if flagged else "pass", claims=claims)


def _annotate_with_search(ctx, flagged: list[FactCheckClaim]):
    """Optional: if a non-mock search provider is configured, verify flagged
    claims against web results and append the note."""
    pid = ctx.router.defaults.get("search")
    if not pid or pid == "mock" or f"search/{pid}" not in ctx.router.registry:
        return
    for claim in flagged:
        try:
            res = ctx.router.call("search", {"query": claim.text})
            snippets = "; ".join(r.get("snippet", "")[:120] for r in res.get("results", [])[:3])
            if snippets:
                claim.note = f"поиск: {snippets}"  # type: ignore[assignment]
        except Exception:  # noqa: BLE001 — search must never break the script pass
            return
