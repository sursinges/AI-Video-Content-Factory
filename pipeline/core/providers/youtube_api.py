"""YouTube publish provider (real). Activates when the owner drops
client_secret*.json into pipeline/ (Google Cloud OAuth Desktop client).

Flow (first upload per account): run_local_server opens the browser for the
Google login — token is stored in data/tokens/<oauth_profile>.json and reused.
Capabilities: upload with full metadata, set thumbnail, schedule via
publish_at (RFC 3339), privacy status, category. Account pool is handled by
M6 (each account = own oauth_profile + proxy)."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


def _client_secret() -> Path:
    root = Path(__file__).resolve().parents[1]
    for f in root.glob("client_secret*.json"):
        return f
    raise ProviderError(
        "youtube_api: нет client_secret*.json в pipeline/ — получи OAuth-клиент "
        "(Desktop) в Google Cloud Console с включённым YouTube Data API v3")


class YoutubeApiProvider(Provider):
    adapter = "youtube_api"

    def _credentials(self, oauth_profile: str):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        import os as _os
        tokens_dir = _os.environ.get("YOUTUBE_TOKENS_DIR") or (Path(__file__).resolve().parents[1] / "data" / "tokens")
        token_file = Path(tokens_dir) / f"{oauth_profile}.json"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        creds = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_secrets_file(str(_client_secret()), SCOPES)
            creds = flow.run_local_server(port=0)  # opens the browser ONCE per account
            token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def execute(self, payload: dict) -> dict:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        meta = payload.get("metadata") or {}
        account = payload.get("account") or {}
        video_path = payload.get("video_path")
        if not video_path or not Path(video_path).exists():
            raise ProviderError("youtube_api: video file missing")
        creds = self._credentials(str(account.get("oauth_profile", "acc1")))
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": (meta.get("title") or "Untitled")[:100],
                "description": meta.get("description", ""),
                "tags": meta.get("tags", [])[:30],
                "categoryId": "27",  # Education
            },
            "status": {
                "privacyStatus": payload.get("visibility", "unlisted"),
                "selfDeclaredMadeForKids": bool((meta.get("youtube") or {}).get("made_for_kids", False)),
            },
        }
        publish_at = payload.get("publish_at") or (meta.get("youtube") or {}).get("publish_at")
        if publish_at:
            body["status"]["publishAt"] = publish_at  # RFC 3339 UTC, requires private/unlisted

        media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True,
                                mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", media_body=media, body=body)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"upload {int(status.progress() * 100)}%")
        video_id = response["id"]

        # thumbnail
        thumb = (meta.get("thumbnail") or {}).get("asset")
        if thumb and Path(thumb).exists():
            youtube.thumbnails().set(videoId=video_id, media_body=thumb).execute()

        return {"video_id": video_id, "visibility": payload.get("visibility", "unlisted"),
                "status": "done", "uploaded_at": self._now()}
