"""Exercise the proposed partner API locally, printing counts rather than records.

Use SEHATI_PARTNER_API_KEY or --key-file PATH containing only the one-time key.
No argument accepts a secret directly. Records are held in memory only; the
script never sends requests outside localhost and never prints the credential.
"""
import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx


def fetch_snapshot(base_url, key, limit=100):
    target = urlsplit(base_url)
    if (target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost"}
            or target.username or target.password or target.path not in {"", "/"}
            or target.query or target.fragment):
        raise ValueError("This inspection client only accepts a local http://127.0.0.1 or http://localhost origin.")
    with httpx.Client(base_url=base_url.rstrip("/"), headers={"X-API-Key": key}, timeout=30,
                      follow_redirects=False, trust_env=False) as client:
        status = client.get("/api/partner/v1/status")
        status.raise_for_status()
        for _ in range(3):
            records, offset, revision, pages = [], 0, None, 0
            while True:
                params = {"limit": limit, "offset": offset}
                if revision is not None:
                    params["data_version"] = revision
                response = client.get("/api/partner/v1/deliveries", params=params)
                if response.status_code == 409:
                    break
                response.raise_for_status()
                payload = response.json()
                records.extend(payload["data"])
                revision = payload["meta"]["data_version"]
                pages += 1
                offset = payload["meta"]["next_offset"]
                if offset is None:
                    if len(records) != payload["meta"]["total"] or len({row["id"] for row in records}) != len(records):
                        raise ValueError("Snapshot count or identifiers failed validation.")
                    return {"records": len(records), "pages": pages, "data_version": revision,
                            "contract": status.json()["contract"], "external_partner_connected": False}
        raise ValueError("Data kept changing. Retry after imports finish.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--page-size", type=int, default=100, choices=range(1, 101), metavar="1..100")
    args = parser.parse_args()
    try:
        key = args.key_file.read_text(encoding="utf-8-sig").strip() if args.key_file else os.environ.get("SEHATI_PARTNER_API_KEY", "").strip()
        if not key:
            raise ValueError("Set SEHATI_PARTNER_API_KEY or provide a private --key-file.")
        summary = fetch_snapshot(args.base_url, key, args.page_size)
    except httpx.HTTPStatusError as exc:
        print(f"API check failed: HTTP {exc.response.status_code}. No data or credentials printed.", file=sys.stderr)
        return 1
    except (ValueError, OSError, httpx.HTTPError) as exc:
        # Avoid exception rendering from network libraries, which may include URLs.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"API check failed: {message}", file=sys.stderr)
        return 1
    print(f"Local API OK: {summary['records']} records, {summary['pages']} pages, data version {summary['data_version']}.")
    print("Contract: Sehati v1. No external partner connection was attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
