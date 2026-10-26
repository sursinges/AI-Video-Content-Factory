"""LLM dramaturgy critic (S1-04). In dry-run returns None (machine-only)."""

from modules.m1_script.prompts import extract_json, render


def llm_critic_issues(ctx, base_vars: dict, chunk_text: str, part_idea: str,
                      machine_issues: list[str]) -> list[str] | None:
    if ctx.dry_run:
        return None
    variables = base_vars | {
        "chunk_text": chunk_text,
        "part_idea": part_idea,
        "forbidden_phrases": ", ".join(f"«{p}»" for p in base_vars.get("_skeleton_phrases", [])),
        "extra": ("Замечания машинного валидатора, которые уже подтверждены: "
                  + "; ".join(machine_issues)) if machine_issues else "",
    }
    resp = ctx.router.call("llm", {"prompt": render("critic_drama.md", variables), "temperature": 0.2})
    data = extract_json(resp.get("text", ""))
    if not data:
        return None  # unparseable verdict → machine-only decision
    return [] if data.get("pass") else [str(i) for i in data.get("issues", [])]
