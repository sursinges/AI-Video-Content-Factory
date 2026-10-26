"""M1 script module (S1): skeleton -> chunk chain -> critic loop -> factcheck."""

from core.contracts import FactCheck, Script, ScriptChunk
from modules.base import Artifact, Module, RunContext
from modules.m1_script.chunks import gen_chunk
from modules.m1_script.critic import llm_critic_issues
from modules.m1_script.factcheck import factcheck_chunk
from modules.m1_script.skeleton import compute_parts, gen_skeleton
from modules.m1_script.validator import validate


class M1Script(Module):
    name = "m1_script"

    def run(self, ctx: RunContext) -> list[Artifact]:
        profile = ctx.profile
        s = profile.get("script", {})
        cc = s.get("chunk_chars", [6000, 9000])
        max_iter = s.get("max_critic_iterations", 3)

        # own-script mode: owner pasted a ready script — chunk it directly,
        # no skeleton/LLM (fully validated the same way)
        if getattr(ctx.manifest, "own_script", None):
            return self._own_script_artifacts(ctx, profile)

        n_parts, body_count, min_chars, max_chars = compute_parts(ctx.manifest, profile)
        sk = gen_skeleton(ctx, n_parts, body_count, min_chars, max_chars)

        # 1) draft pass: generate every chunk in order (mid/final need prev text)
        texts: dict[int, str] = {}
        forms: dict[int, int] = {}
        roles: dict[int, str] = {}
        from modules.m1_script.vars import part_role, pick_form

        for part in range(1, n_parts + 1):
            roles[part] = part_role(part, n_parts)
            forms[part] = pick_form(part, roles[part], n_parts)
            texts[part] = gen_chunk(ctx, sk, part, prev_text=texts.get(part - 1))

        # 2) critic loop: machine validator + LLM critic; failures regenerate the chunk
        critic_pass: dict[int, bool] = {}
        from modules.m1_script.vars import base_vars

        base = base_vars(ctx.manifest, profile, min_chars, max_chars)
        base["_skeleton_phrases"] = sk.forbidden_phrases
        for part in range(1, n_parts + 1):
            for _ in range(max_iter):
                machine = validate(
                    texts[part], role=roles[part], form=forms[part],
                    prev_form=forms.get(part - 1) if roles[part] == "body" else None,
                    min_chars=min_chars, max_chars=max_chars,
                    stop_words=profile.get("stop_words", []),
                    forbidden_phrases=sk.forbidden_phrases,
                    final_phrase=profile.get("final_phrase", "Спокойной ночи."),
                    channel_name=profile.get("name", ""), address=profile.get("address", "ты"),
                )
                part_idea = sk.ideas[part - 2] if roles[part] == "body" else ctx.manifest.topic
                llm_issues = llm_critic_issues(ctx, base, texts[part], part_idea, machine)
                issues = machine + (llm_issues or [])
                if not issues:
                    critic_pass[part] = True
                    break
                texts[part] = gen_chunk(ctx, sk, part, prev_text=texts.get(part - 1), issues=issues)
            else:
                critic_pass[part] = False  # keep best effort, flag for review

        # 3) fact-check each chunk
        factchecks: dict[int, FactCheck] = {}
        for part in range(1, n_parts + 1):
            factchecks[part] = factcheck_chunk(ctx, base, texts[part])

        chunks = [
            ScriptChunk(part=p, role=roles[p], form=forms[p], text=texts[p],
                        char_count=len(texts[p]), critic_pass=critic_pass[p],
                        factcheck=factchecks[p])
            for p in range(1, n_parts + 1)
        ]
        script = Script(
            title_working=ctx.manifest.topic,
            hook_summary=sk.description,
            chunks=chunks,
            full_text_char_count=sum(c.char_count for c in chunks),
        )
        return [("script/skeleton.json", sk), ("script/script.json", script)]

    def _own_script_artifacts(self, ctx: RunContext, profile: dict) -> list[Artifact]:
        from core.contracts import Skeleton
        from core.script_cleaner import clean_script_text
        from modules.m2_audio.runner import segment_text
        from modules.m1_script.vars import part_role, pick_form

        raw_text = ctx.manifest.own_script.strip()
        text = clean_script_text(raw_text) or raw_text
        cc = profile.get("script", {}).get("chunk_chars", [6000, 9000])
        max_chars = cc[1]
        segs = segment_text(text, max_chars) or [text]
        chunks = []
        for i, seg in enumerate(segs, start=1):
            role = part_role(i, len(segs))
            chunks.append(ScriptChunk(
                part=i, role=role, form=pick_form(i, role, len(segs)),
                text=seg, char_count=len(seg), critic_pass=True,
                factcheck=FactCheck(status="pass")))
        sk = Skeleton(description="OWN SCRIPT (owner-provided)", anchors=["-"] * 4,
                      chunks_with_examples=[], forms=["-"], ideas=["-"] * max(1, len(segs) - 2),
                      number_of_parts=len(segs), body_parts_count=max(1, len(segs) - 2))
        script = Script(title_working=ctx.manifest.topic, hook_summary="own script",
                        chunks=chunks, full_text_char_count=sum(c.char_count for c in chunks))
        return [("script/skeleton.json", sk), ("script/script.json", script)]
