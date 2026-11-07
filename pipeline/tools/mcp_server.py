"""Minimal MCP (Model Context Protocol) stdio server for pipeline — one-click
connect for Claude Desktop / Claude Code / Codex CLI / ZCode. Line-delimited
JSON-RPC 2.0 over stdio.

Tools exposed: list_runs, run_status, create_episode, resume_run, doctor.
Run:  python tools/mcp_server.py      (configured via claude_desktop_config.json
or ~/.codex/config.toml — ready-to-paste configs: GET /api/mcp/clients on the UI)
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOOLS = [
    {"name": "list_runs", "description": "List recent pipeline episodes with status",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "run_status", "description": "Steps + artifacts of one episode run",
     "inputSchema": {"type": "object",
                     "properties": {"run_id": {"type": "string"}},
                     "required": ["run_id"]}},
    {"name": "create_episode", "description": "Launch a new episode (topic or own script)",
     "inputSchema": {"type": "object",
                     "properties": {"topic": {"type": "string"}, "minutes": {"type": "number"},
                                    "script": {"type": "string"}},
                     "required": []}},
    {"name": "resume_run", "description": "Resume a failed/interrupted episode from its last completed stage",
     "inputSchema": {"type": "object",
                     "properties": {"run_id": {"type": "string"}},
                     "required": ["run_id"]}},
    {"name": "doctor", "description": "System diagnostics: python, ffmpeg, edition, keys",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _state():
    from core.state import StateDB
    return StateDB(ROOT / "data" / "state.db")


def tool_list_runs(_args):
    st = _state()
    rows = st.conn.execute("SELECT run_id, status, created_at FROM runs ORDER BY created_at DESC LIMIT 20").fetchall()
    st.close()
    return [{"run_id": r["run_id"], "status": r["status"]} for r in rows]


def tool_run_status(args):
    st = _state()
    steps = st.conn.execute("SELECT step, status, error FROM steps WHERE run_id=?", (args["run_id"],)).fetchall()
    st.close()
    return [{"step": s["step"], "status": s["status"], "error": s["error"]} for s in steps]


def _ui_post(path: str, body: dict) -> dict:
    import urllib.request

    req = urllib.request.Request(f"http://127.0.0.1:8765{path}",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def tool_create_episode(args):
    try:
        return _ui_post("/api/episode", {"topic": args.get("topic") or "",
                                         "target_minutes": args.get("minutes", 1),
                                         "own_script": args.get("script") or ""})
    except Exception as e:  # noqa: BLE001
        return {"error": f"UI server on :8765 unreachable ({e}) — start it with 'pipeline ui'"}


def tool_resume_run(args):
    try:
        return _ui_post(f"/api/run/{args['run_id']}/resume", {})
    except Exception as e:  # noqa: BLE001
        return {"error": f"UI server on :8765 unreachable ({e}) — start it with 'pipeline ui'"}


def tool_doctor(_args):
    from core.diagnostics import run_diagnostics

    report = run_diagnostics(ROOT)
    return {"overall": report["overall"],
            "checks": [{"name": c["name"], "status": c["status"], "detail": c.get("detail", "")}
                       for c in report["checks"]]}


HANDLERS = {"list_runs": tool_list_runs, "run_status": tool_run_status,
            "create_episode": tool_create_episode, "resume_run": tool_resume_run,
            "doctor": tool_doctor}


def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        rid = req.get("id")
        resp = {"jsonrpc": "2.0", "id": rid}
        if method == "initialize":
            resp["result"] = {"protocolVersion": "2024-11-05",
                              "capabilities": {"tools": {}},
                              "serverInfo": {"name": "pipeline", "version": "0.4"}}
        elif method == "tools/list":
            resp["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            params = req.get("params") or {}
            fn = HANDLERS.get(params.get("name", ""))
            try:
                result = fn((params.get("arguments") or {}))
                resp["result"] = {"content": [{"type": "text",
                                               "text": json.dumps(result, ensure_ascii=False)}]}
            except Exception as e:  # noqa: BLE001
                resp["result"] = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
        elif method == "notifications/initialized":
            continue
        else:
            resp["error"] = {"code": -32601, "message": "method not found"}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
