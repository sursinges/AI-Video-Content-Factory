"""RU/EN interface strings. Stage 2 exposes the same dictionaries in the UI."""

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "run_started": "Прогон {run_id} запущен (режим: {mode})",
        "step_done": "Шаг {step} — готово ({artifact})",
        "step_skip": "Шаг {step} — уже выполнен, пропускаю",
        "step_fail": "Шаг {step} — ошибка: {error}",
        "run_finished": "Прогон {run_id} завершён",
        "run_failed": "Прогон {run_id} прерван на шаге {step}",
        "no_runs": "Прогонов нет",
        "cache_hit": "Кэш-попадание ({ptype}/{provider})",
        "budget_stop": "Бюджет прогона исчерпан: {spent} >= {limit}. Вызов остановлен.",
        "paid_needs_flag": "Платный провайдер {provider} требует явного разрешения (budget_limit_usd > 0).",
    },
    "en": {
        "run_started": "Run {run_id} started (mode: {mode})",
        "step_done": "Step {step} — done ({artifact})",
        "step_skip": "Step {step} — already done, skipping",
        "step_fail": "Step {step} — failed: {error}",
        "run_finished": "Run {run_id} finished",
        "run_failed": "Run {run_id} failed at step {step}",
        "no_runs": "No runs",
        "cache_hit": "Cache hit ({ptype}/{provider})",
        "budget_stop": "Run budget exhausted: {spent} >= {limit}. Call stopped.",
        "paid_needs_flag": "Paid provider {provider} requires explicit opt-in (budget_limit_usd > 0).",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    return STRINGS.get(lang, STRINGS["en"])[key].format(**kwargs)
