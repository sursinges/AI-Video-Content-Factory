"""One-time YouTube account connect (OAuth). Run via UI or CLI:

    python tools/youtube_connect.py --profile acc1 [--proxy http://127.0.0.1:10809]

Opens the browser for the Google login, saves the token to
data/tokens/<profile>.json, prints the connected channel. Requires
client_secret*.json in pipeline/ (Google Cloud OAuth Desktop client).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="acc1")
    ap.add_argument("--secret", default=None, help="path to client_secret*.json")
    ap.add_argument("--proxy", default=None, help="proxy for the OAuth browser, e.g. http://127.0.0.1:10809")
    args = ap.parse_args()

    secrets = list(ROOT.glob("client_secret*.json"))
    if args.secret:
        secrets = [Path(args.secret)]
    if not secrets:
        raise SystemExit("Нет client_secret*.json в pipeline/ — см. инструкцию в UI (Инструменты → Публикация)")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow_kwargs = {"scopes": SCOPES}
    if args.proxy:
        # proxy for the OAuth browser session (per-account identity)
        import os

        os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = args.proxy
        os.environ["ALL_PROXY"] = args.proxy
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets[0]), **flow_kwargs)
    creds = flow.run_local_server(port=0, open_browser=True)

    import os
    token_dir = os.environ.get("YOUTUBE_TOKENS_DIR") or (ROOT / "data" / "tokens")
    token_dir.mkdir(parents=True, exist_ok=True)
    token_file = token_dir / f"{args.profile}.json"
    token_file.write_text(creds.to_json(), encoding="utf-8")

    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=creds)
    ch = youtube.channels().list(part="snippet", mine=True).execute()
    items = ch.get("items", [])
    if items:
        print(f"Подключён канал: {items[0]['snippet']['title']} ({items[0]['id']})")
    print(f"Токен сохранён: {token_file}")


if __name__ == "__main__":
    main()
