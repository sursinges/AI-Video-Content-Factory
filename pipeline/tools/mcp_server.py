"""Minimal MCP (Model Context Protocol) stdio server for pipeline — one-click
connect for Claude Desktop / ZCode. Line-delimited JSON-RPC 2.0 over stdio.

Tools exposed: list_runs, run_status, create_episode.
Run:  python tools/mcp_server.py      (configured via claude_desktop_config.json)
"""

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOOLS = [
    {"name": "list_runs", "description": "List recent pipeline episodes with status",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "run_status", "description": "Steps + artifacts of one episode run",
     "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}},
                     "required": ["run_id"]}},
    {"name": "create_episode", "description": "Launch a new episode (topic or own script)",
     "inputSchema": {"type": "object",
                     "properties": {"topic": {"type": "string"}, "minutes": {"type": "number"},
                                    "script": {"type": "string"}},
                     "required": []}},
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


def tool_create_episode(args):
    body = json.dumps({"topic": args.get("topic") or "", "target_minutes": args.get("minutes", 1),
                       "own_script": args.get("script") or ""}).encode("utf-8")
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8765/api/episode", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"UI server on :8765 unreachable ({e}) — start it with 'pipeline ui'"}


HANDLERS = {"list_runs": tool_list_runs, "run_status": tool_run_status,
            "create_episode": tool_create_episode}


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
