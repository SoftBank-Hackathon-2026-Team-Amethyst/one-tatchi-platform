#!/usr/bin/env python3
"""Read-only external continuity probe; logs status/latency, never guestbook contents."""
import argparse
import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


def probe(url, marker):
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            body = response.read(2_000_000)
            ok = response.status == 200 and (not marker or marker.encode() in body)
            return {"ok": ok, "status": response.status, "ms": round((time.monotonic() - started) * 1000)}
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test-url", required=True)
    p.add_argument("--prod-url", required=True)
    p.add_argument("--test-marker", required=True)
    p.add_argument("--prod-marker", required=True)
    p.add_argument("--minutes", type=int, default=35)
    p.add_argument("--output", type=Path, default=Path("probe.jsonl"))
    a = p.parse_args()
    if not 30 <= a.minutes <= 60 or not a.test_marker or not a.prod_marker or a.test_marker == a.prod_marker:
        p.error("use 30–60 minutes and different nonempty DB markers")
    checks = []
    for env, url, marker in (("test", a.test_url, a.test_marker), ("prod", a.prod_url, a.prod_marker)):
        if not re.fullmatch(r"https://[a-z0-9-]+\.trycloudflare\.com/?", url):
            p.error("expected a public HTTPS Quick Tunnel URL")
        checks.extend([(env, url.rstrip("/") + "/", ""), (env + "-db", url.rstrip("/") + "/api/guestbook", marker)])
    start, failed, rounds = time.monotonic(), 0, 0
    with a.output.open("w") as stream, concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while time.monotonic() - start < a.minutes * 60:
            futures = [pool.submit(probe, url, marker) for _, url, marker in checks]
            results = {name: future.result() for (name, _, _), future in zip(checks, futures)}
            failed += sum(not result["ok"] for result in results.values())
            stream.write(json.dumps({"time": time.time(), "elapsed": round(time.monotonic() - start, 2), "checks": results}) + "\n")
            stream.flush()
            rounds += 1
            time.sleep(max(0, start + rounds * 5 - time.monotonic()))
    print(json.dumps({"rounds": rounds, "failed_requests": failed, "elapsed_seconds": round(time.monotonic() - start)}))
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
