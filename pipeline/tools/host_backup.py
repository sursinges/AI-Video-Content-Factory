"""Host backup utility (P5-06): archives users.db, host config and every
tenant data tree into backups/host_backup_YYYYMMDD_HHMM.zip.

    python tools/host_backup.py            # keep last 14 by default
    python tools/host_backup.py --keep 30

Restore: unzip over the workspace root (paths inside are relative to it).
Run it from Task Scheduler / cron for periodic backups — the hosted data
lives only on this machine until you wire external storage."""

import argparse
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INCLUDE_FILES = ["data/users.db", "config/channel.profile.yaml", "config/providers.yaml",
                 "config/ui_settings.yaml", "config/formats.yaml", "config/accounts.yaml"]
INCLUDE_DIRS = ["config/profiles", "config/presets", "notes", "transcripts"]
TENANT_INCLUDE = ["config", "data/state.db", "data/library.db", "data/voices.json",
                  "data/tokens", "runs", "notes", "transcripts", ".env"]


def add_to_zip(zf: zipfile.ZipFile, path: Path, arcname: str):
    if path.is_file():
        zf.write(path, arcname)
    elif path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                zf.write(f, str(Path(arcname) / f.relative_to(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=14, help="how many backups to keep")
    ap.add_argument("--remote", default="", help="rclone remote for offsite copy, e.g. 'b2:pipeline-backups'")
    args = ap.parse_args()

    out_dir = ROOT / "backups"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M")
    out = out_dir / f"host_backup_{stamp}.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_FILES:
            add_to_zip(zf, ROOT / rel, rel)
        for rel in INCLUDE_DIRS:
            add_to_zip(zf, ROOT / rel, rel)
        tenants_root = ROOT / "data" / "tenants"
        if tenants_root.exists():
            for tdir in sorted(p for p in tenants_root.iterdir() if p.is_dir()):
                for rel in TENANT_INCLUDE:
                    add_to_zip(zf, tdir / rel, f"data/tenants/{tdir.name}/{rel}")

    backups = sorted(out_dir.glob("host_backup_*.zip"))
    for old in backups[:-args.keep] if args.keep > 0 else []:
        old.unlink()
    print(f"OK: {out.name} ({out.stat().st_size / 1e6:.1f} MB), kept {min(len(backups), args.keep)}")
    if args.remote:
        import subprocess as _sp
        r = _sp.run(["rclone", "copy", str(out), f"{args.remote}/{out.name}"],
                    capture_output=True, text=True)
        print("offsite:", "OK" if r.returncode == 0 else f"rclone failed: {r.stderr[:200]}")


if __name__ == "__main__":
    main()
