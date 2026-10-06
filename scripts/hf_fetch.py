#!/usr/bin/env python3
"""
hf_fetch.py -- resumable, verified download of a Hugging Face model repo over plain HTTPS ranges.

Written for this box after `huggingface_hub`'s xet client stalled on it: systemd-resolved here also
asks Tailscale's MagicDNS, which answers SERVFAIL for Hugging Face's CDN hosts, so lookups fail
intermittently or take 5 s, and the xet client gives up on them. This script

  * resolves through the system first and falls back to the LAN resolvers by `dig` (and caches the
    answer), so one bad lookup costs nothing;
  * downloads each LFS file in fixed-size ranges into a preallocated `.part` file, recording finished
    ranges in a state file, so an interrupted run resumes range-exact;
  * checks every finished file against the repository's LFS SHA-256 before it is renamed into place,
    and starts the file over if it does not match.

  python scripts/hf_fetch.py --repo MomonV/DeepSeek-V4.1-Flash-UNCENSORED-NVFP4 \
      --revision 1dec890b... --dir deepseek-v41-uncensored --workers 8

Exit 0 when every file is present and verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

FALLBACK_DNS = ("192.168.20.11", "192.168.20.12", "1.1.1.1")
_orig_gai = socket.getaddrinfo
_dns_cache: dict[str, list[str]] = {}
_dns_lock = threading.Lock()


def _dig(host: str) -> list[str]:
    for server in FALLBACK_DNS:
        try:
            out = subprocess.run(["dig", "+short", "+tries=1", "+time=3", f"@{server}", host, "A"],
                                 capture_output=True, text=True, timeout=8).stdout
            ips = [x for x in out.split() if x.count(".") == 3 and x.replace(".", "").isdigit()]
            if ips:
                return ips
        except Exception:  # noqa: BLE001
            pass
    return []


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_gai(host, port, family, type, proto, flags)
    except socket.gaierror:
        if not isinstance(host, str):
            raise
        with _dns_lock:
            ips = _dns_cache.get(host) or _dig(host)
            if ips:
                _dns_cache[host] = ips
        if not ips:
            raise
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]


socket.getaddrinfo = _getaddrinfo


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def retry(fn, what: str, tries: int = 60):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            wait = min(2 ** min(i, 6), 60)
            log(f"retry {i + 1}/{tries} {what}: {type(e).__name__}: {str(e)[:120]} (sleep {wait}s)")
            time.sleep(wait)


def list_files(repo: str, revision: str) -> list[dict]:
    url = f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true"
    tree = json.loads(retry(lambda: http_get(url), "list files"))
    return [x for x in tree if x["type"] == "file"]


class FileJob:
    def __init__(self, root: str, repo: str, revision: str, entry: dict, chunk: int):
        self.path = entry["path"]
        self.size = entry["size"]
        self.sha = (entry.get("lfs") or {}).get("oid")
        self.url = f"https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(self.path)}"
        self.final = os.path.join(root, self.path)
        work = os.path.join(root, ".fetch")
        self.part = os.path.join(work, self.path.replace("/", "__") + ".part")
        self.state = self.part + ".json"
        self.chunk = chunk
        self.n = max(1, -(-self.size // chunk))
        self.done: set[int] = set()
        self.lock = threading.Lock()
        os.makedirs(work, exist_ok=True)
        os.makedirs(os.path.dirname(self.final) or root, exist_ok=True)

    def verified_marker(self) -> str:
        return self.part + ".verified"

    def complete(self) -> bool:
        return os.path.isfile(self.final) and os.path.getsize(self.final) == self.size and (
            self.sha is None or os.path.isfile(self.verified_marker()))

    def prepare(self) -> list[int]:
        if os.path.isfile(self.state) and os.path.isfile(self.part) and os.path.getsize(self.part) == self.size:
            self.done = set(json.load(open(self.state))["done"])
        else:
            with open(self.part, "wb") as f:
                f.truncate(self.size)
            self.done = set()
            self._save()
        return [i for i in range(self.n) if i not in self.done]

    def _save(self) -> None:
        tmp = self.state + ".tmp"
        json.dump({"size": self.size, "chunk": self.chunk, "done": sorted(self.done)}, open(tmp, "w"))
        os.replace(tmp, self.state)

    def fetch(self, i: int) -> int:
        """Stream range i into the .part file, resuming at the exact byte after a dropped connection:
        a reset 100 MB into a 128 MB range costs the 28 MB still missing, not the whole range."""
        a = i * self.chunk
        b = min(self.size, a + self.chunk)
        pos = [a]
        fd = os.open(self.part, os.O_WRONLY)

        def one():
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={pos[0]}-{b - 1}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status != 206:
                    raise IOError(f"HTTP {r.status} for a range request")
                while pos[0] < b:
                    blk = r.read(min(4 << 20, b - pos[0]))
                    if not blk:
                        raise IOError(f"connection closed at {pos[0] - a} of {b - a} bytes")
                    os.pwrite(fd, blk, pos[0])
                    pos[0] += len(blk)

        try:
            retry(one, f"{self.path} [{i + 1}/{self.n}]")
        finally:
            os.close(fd)
        with self.lock:
            self.done.add(i)
            self._save()
        return b - a

    def finish(self) -> bool:
        if self.sha:
            h = hashlib.sha256()
            with open(self.part, "rb") as f:
                while True:
                    blk = f.read(64 << 20)
                    if not blk:
                        break
                    h.update(blk)
            if h.hexdigest() != self.sha:
                log(f"SHA MISMATCH {self.path}: starting it over")
                os.unlink(self.part)
                os.unlink(self.state)
                return False
        os.replace(self.part, self.final)
        open(self.verified_marker(), "w").write(self.sha or "")
        if os.path.exists(self.state):
            os.unlink(self.state)
        return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--revision", default="main")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk-mb", type=int, default=128)
    a = ap.parse_args(argv)

    files = list_files(a.repo, a.revision)
    total = sum(f["size"] for f in files)
    log(f"{a.repo}@{a.revision[:12]}: {len(files)} files, {total / 1e9:.1f} GB")
    # small files first (config, tokenizer, code), then the shards in order
    files.sort(key=lambda f: (f["size"] > 64 << 20, f["path"]))
    jobs = [FileJob(a.dir, a.repo, a.revision, f, a.chunk_mb << 20) for f in files]

    # files another downloader already finished: keep them if their hash says so
    for j in jobs:
        if j.sha and not j.complete() and os.path.isfile(j.final) and os.path.getsize(j.final) == j.size:
            h = hashlib.sha256()
            with open(j.final, "rb") as f:
                while blk := f.read(64 << 20):
                    h.update(blk)
            if h.hexdigest() == j.sha:
                open(j.verified_marker(), "w").write(j.sha)
                log(f"already present and verified: {j.path}")
            else:
                log(f"present but hash differs, will refetch: {j.path}")
                os.unlink(j.final)

    got = sum(j.size for j in jobs if j.complete())
    t0, got0 = time.time(), got
    stats_lock = threading.Lock()
    last = [time.time()]

    for attempt in range(3):
        pending = [j for j in jobs if not j.complete()]
        if not pending:
            break
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for j in pending:
                todo = j.prepare()
                if not todo and j.finish():
                    continue
                futs = [ex.submit(j.fetch, i) for i in todo]
                for fu in as_completed(futs):
                    n = fu.result()
                    with stats_lock:
                        got += n
                        if time.time() - last[0] > 60:
                            last[0] = time.time()
                            rate = (got - got0) / max(1.0, time.time() - t0)
                            eta = (total - got) / max(rate, 1)
                            log(f"{got / 1e9:.1f}/{total / 1e9:.1f} GB  {rate / 1e6:.1f} MB/s  ETA {eta / 3600:.1f} h  ({j.path})")
                ok = j.finish()
                log(f"{'verified' if ok else 'RETRY'} {j.path} ({j.size / 1e9:.2f} GB)")
    missing = [j.path for j in jobs if not j.complete()]
    if missing:
        log(f"INCOMPLETE: {len(missing)} files, first {missing[0]}")
        return 1
    log(f"all {len(jobs)} files present and verified in {(time.time() - t0) / 3600:.2f} h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
