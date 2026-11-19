#!/usr/bin/env python3
"""Backup/restore dari command line (bisa dipakai saat server mati).

  backup.py create [--label manual]
  backup.py list
  backup.py verify NAMA
  backup.py restore NAMA [--with-metadata]   (hentikan server dulu bila --with-metadata)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import build_settings  # noqa: E402
from backend.services.backup_service import BackupService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--label", default="manual")
    sub.add_parser("list")
    v = sub.add_parser("verify")
    v.add_argument("name")
    r = sub.add_parser("restore")
    r.add_argument("name")
    r.add_argument("--with-metadata", action="store_true")
    a = ap.parse_args()
    svc = BackupService(build_settings())
    if a.cmd == "create":
        out = svc.create_sync(a.label)
    elif a.cmd == "list":
        out = svc.list()
    elif a.cmd == "verify":
        out = svc.verify(a.name)
    else:
        out = svc.restore_sync(a.name, a.with_metadata)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
