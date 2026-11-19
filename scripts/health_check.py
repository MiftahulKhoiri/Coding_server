#!/usr/bin/env python3
"""Health check CODING_SERVER + status engine (pemeriksaan nyata, bukan asumsi).

Pemakaian:
  health_check.py [--url http://127.0.0.1:8800]   cek server yang berjalan
  health_check.py --engines                         cek compiler/runtime lokal saja
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_engines() -> int:
    from backend.core.sandbox import bwrap_available
    from backend.engines.registry import get_registry

    bad = 0
    for st in get_registry().statuses(refresh=True):
        mark = "OK " if st["status"] == "AVAILABLE" else "-- "
        bad += st["status"] != "AVAILABLE"
        print(f"  {mark}{st['language']:<24} {st['status']:<14} {st.get('version') or ''}")
    print(f"  Sandbox bubblewrap: {'AVAILABLE' if bwrap_available() else 'NOT_AVAILABLE'}")
    return bad


def check_server(url: str) -> int:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/v1/system/health", timeout=5) as r:
            data = json.loads(r.read())
        print(f"  Backend: {data['status']} (versi {data['version']}, sandbox={data['sandbox']}, db={data['database']})")
        return 0 if data["status"] == "ok" else 1
    except Exception as e:
        print(f"  Backend: TIDAK MENJAWAB ({e})")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--engines", action="store_true")
    a = ap.parse_args()
    rc = 0
    if a.url or not a.engines:
        rc |= check_server(a.url or "http://127.0.0.1:8800")
    if a.engines:
        print("Engine:")
        check_engines()
    return rc


if __name__ == "__main__":
    sys.exit(main())
