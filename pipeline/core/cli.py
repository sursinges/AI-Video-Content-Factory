import sys
from pathlib import Path

import typer
import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.i18n import tr

app = typer.Typer(add_completion=False, help="AI video production pipeline")


def _workspace() -> Path:
    return Path(__file__).resolve().parent.parent


def _lang() -> str:
    cfg = _workspace() / "config" / "providers.yaml"
    try:
        return yaml.safe_load(cfg.read_text(encoding="utf-8")).get("interface_lang", "en")
    except Exception:  # noqa: BLE001 — missing config must not break the CLI
        return "en"


@app.command()
def run(manifest: Path, until: str = typer.Option(None, help="stop after this step (e.g. m2_audio)"),
        dry_run: bool = typer.Option(False, help="mock providers, no network/keys")):
    """Run a full episode conveyor from a manifest YAML/JSON."""
    from core.orchestrator import Orchestrator

    orch = Orchestrator(_workspace(), lang=_lang(), on_event=print)
    try:
        orch.run(manifest, until=until, dry_run=dry_run)
    finally:
        orch.close()


@app.command()
def status(run_id: str = typer.Argument(None)):
    """Show all runs or one run's steps."""
    from core.orchestrator import Orchestrator

    lang = _lang()
    orch = Orchestrator(_workspace(), lang=lang)
    try:
        runs = orch.status(run_id)
        if not runs:
            print(tr(lang, "no_runs"))
            return
        for r in runs:
            print(f"{r['run_id']}  [{r['status']}]")
            for step, info in r["steps"].items():
                mark = {"done": "OK", "failed": "FAIL", "pending": "..", "running": ">>"}.get(
                    info["status"], info["status"])
                line = f"  {mark:>4}  {step}"
                if info["error"]:
                    line += f"  — {info['error']}"
                print(line)
    finally:
        orch.close()


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output report as structured JSON"),
):
    """Run system diagnostics: check Python, FFmpeg, CUDA, disk space, and configs."""
    import json
    from core.diagnostics import print_diagnostics_report, run_diagnostics

    report = run_diagnostics(_workspace())
    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_diagnostics_report(report, lang=_lang())

    if report["overall"] == "error":
        raise typer.Exit(code=1)


@app.command()
def resume(
    run_id: str,
    until: str = typer.Option(None, help="Stop after this step (e.g. m4_assembly)"),
    from_step: str = typer.Option(None, "--from-step", help="Re-run starting from this step onwards (e.g. m4_assembly)"),
    dry_run: bool = typer.Option(False, help="Mock providers, no network/keys"),
):
    """Resume an interrupted run or re-run starting from a specific step."""
    from core.orchestrator import Orchestrator

    orch = Orchestrator(_workspace(), lang=_lang(), on_event=print)
    try:
        orch.resume(run_id, until=until, dry_run=dry_run, from_step=from_step)
    finally:
        orch.close()


@app.command()
def ui(port: int = typer.Option(8765, help="Web Studio port"),
       host: str = typer.Option("127.0.0.1", help="Host address (use 0.0.0.0 for LAN/phone access)")):
    """Launch the Web Studio interactive dashboard (FastAPI)."""
    from ui.server import main as ui_main

    ui_main(port, host)


if __name__ == "__main__":
    app()
