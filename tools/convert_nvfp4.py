"""
convert_nvfp4.py -- turn an NVFP4 DeepSeek-V4.1-Flash checkpoint (nvidia/DeepSeek-V4.1-Flash-NVFP4 or
a merge built on it, e.g. MomonV/DeepSeek-V4.1-Flash-UNCENSORED-NVFP4) back into the checkpoint's own
format, the one this engine reads: routed experts as packed FP4 codes plus one UE8M0 scale per 32
weights, in deepseek-ai/DeepSeek-V4.1-Flash's exact shard layout.

Why this is exact, not a requantization. NVIDIA converted the source MXFP4 experts to NVFP4 without
touching a value: every 16-weight NVFP4 scale times the tensor's `weight_scale_2` is the power of two
the 32-weight UE8M0 scale held, both halves of each 32-group carry the same scale, and the FP4 codes are
the source's codes with one exception -- the source stores some zeros as -0 (code 8), NVIDIA stores
them as +0 (code 0). Measured 2026-10-07 on experts of layers 10, 20 and 30 against deepseek-ai's
shards: dequantized values identical, max |diff| 0.0. So the routed experts come back value-exact; only
the sign bit of some zeros differs, which no product or sum can see. This script asserts the
power-of-two and pair conditions on every scale it converts and refuses the shard if one fails.

Layout. Each output shard is written with the reference shard's header bytes verbatim (same tensor
names, dtypes, shapes and byte offsets), so `engine/experts.py` sees the two contiguous runs per expert
it was tuned for and `engine/model.py` finds layer L in shard L + 3 as before. The reference headers
(10.7 MB for all 48 shards) are fetched once from Hugging Face by HTTP range request and cached in
`<out>/.reference-headers.json`; no reference weights are downloaded. Shards that hold no routed
expert and contain the same tensors as the reference (the dense prologue, the DSpark drafter, the two
Engram tables) are hardlinked from the source instead of copied: the engine reads tensors by the
header's offsets, so the order inside those files does not matter.

Everything that is not a routed expert is copied byte for byte from the source, so a merge's patched
tensors (MomonV: `attn.wo_b` and `ffn.shared_experts.w2` of layers 10-36, FP8) carry over unchanged.
With `uncensored_patch_manifest.json` in the source directory each of them is checked against the
manifest's `source_sha256` on the way through.

  python tools/convert_nvfp4.py --src deepseek-v41-uncensored --out deepseek-v41-uncensored/native

Resumable: a shard whose output exists and whose recorded size matches is skipped. `--jobs` shards are
converted in parallel (4 default; the work is I/O and a little CPU per scale tensor).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed

REF_REPO = "deepseek-ai/DeepSeek-V4.1-Flash"
HF = "https://huggingface.co/{repo}/resolve/main/{f}"
EXPERT_RE = re.compile(r"^layers\.\d+\.ffn\.experts\.\d+\.w[123]\.(weight|scale)$")
DTYPE_BYTES = {"F8_E8M0": 1, "F8_E4M3": 1, "I8": 1, "U8": 1, "BF16": 2, "F16": 2, "F32": 4, "I32": 4, "I64": 8}
CHUNK = 64 << 20


# --------------------------------------------------------------------------- helpers

def _get(url: str, a: int | None = None, b: int | None = None, tries: int = 12) -> bytes:
    """HTTP GET (optionally a byte range [a, b)) with retries -- this box's DNS drops lookups at times."""
    last = None
    for i in range(tries):
        try:
            hdr = {"Range": f"bytes={a}-{b - 1}"} if a is not None else {}
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 -- network: retry anything
            last = e
            time.sleep(min(2 ** i, 30))
    raise RuntimeError(f"GET {url} failed after {tries} tries: {last}")


def fetch_reference_headers(cache: str, repo: str = REF_REPO) -> dict:
    """{shard: {"raw": header bytes, "size": file size, "sha256": lfs oid}} for every reference shard."""
    if os.path.isfile(cache):
        d = json.load(open(cache))
    else:
        tree = json.loads(_get(f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true"))
        lfs = {x["path"]: (x["size"], x["lfs"]["oid"]) for x in tree if x.get("lfs") and x["path"].endswith(".safetensors")}
        d = {}
        for f in sorted(lfs):
            url = HF.format(repo=repo, f=f)
            n = struct.unpack("<Q", _get(url, 0, 8))[0]
            raw = _get(url, 8, 8 + n)
            assert len(raw) == n, f"short header read for {f}"
            d[f] = {"header_b64": base64.b64encode(raw).decode(), "size": lfs[f][0], "sha256": lfs[f][1]}
        tmp = cache + ".tmp"
        json.dump(d, open(tmp, "w"))
        os.replace(tmp, cache)
    return {f: {"raw": base64.b64decode(v["header_b64"]), "size": v["size"], "sha256": v["sha256"]} for f, v in d.items()}


def read_header(path: str) -> tuple[int, dict]:
    with open(path, "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        h = json.loads(fh.read(n))
    h.pop("__metadata__", None)
    return 8 + n, h


def nbytes(meta: dict) -> int:
    n = DTYPE_BYTES[meta["dtype"]]
    for s in meta["shape"]:
        n *= s
    return n


def nvfp4_scale_to_ue8m0(ws: bytes, g: bytes, shape16: list[int]) -> bytes:
    """NVFP4 block scales (F8_E4M3 [N, K/16]) x weight_scale_2 (F32 scalar) -> UE8M0 [N, K/32].

    Exact only when each pair of 16-scales is equal and their product with the global scale is a
    power of two; anything else raises (the shard is then not a lossless MXFP4 conversion)."""
    import torch

    n, k16 = shape16
    s = torch.frombuffer(bytearray(ws), dtype=torch.uint8).view(torch.float8_e4m3fn).view(n, k16 // 2, 2).double()
    gs = torch.frombuffer(bytearray(g), dtype=torch.float32).double().item()
    if not torch.equal(s[..., 0], s[..., 1]):
        raise ValueError("NVFP4 scale pair differs inside a 32-group")
    v = s[..., 0] * gs
    if not bool((v > 0).all()):
        # an all-zero group stores scale 0; a UE8M0 cannot say 0, so take the smallest exponent the
        # source format uses for it (the codes are all zero, so any scale gives the same values)
        v = torch.where(v > 0, v, torch.full_like(v, 2.0 ** -127))
    m, e = torch.frexp(v)  # v = m * 2^e, m in [0.5, 1)
    if not bool((m == 0.5).all()):
        raise ValueError("NVFP4 scale x weight_scale_2 is not a power of two")
    b = e.long() - 1 + 127
    if not bool(((b >= 0) & (b <= 254)).all()):
        raise ValueError("UE8M0 exponent out of range")
    return b.to(torch.uint8).numpy().tobytes()


# --------------------------------------------------------------------------- one shard

def convert_shard(src: str, out: str, shard: str, ref_raw: bytes, patch_sha: dict) -> dict:
    t0 = time.time()
    dst = os.path.join(out, shard)
    ref = json.loads(ref_raw)
    ref.pop("__metadata__", None)
    base = 8 + len(ref_raw)
    size = base + max(v["data_offsets"][1] for v in ref.values())

    src_path = os.path.join(src, shard)
    sbase, sh = read_header(src_path)
    if os.path.isfile(dst) and os.path.getsize(dst) == size:
        return {"shard": shard, "skipped": True}

    routed = any(EXPERT_RE.match(k) for k in ref)
    same_set = {k: (v["dtype"], v["shape"]) for k, v in ref.items()} == {k: (v["dtype"], v["shape"]) for k, v in sh.items()}
    if not routed and same_set:
        if os.path.exists(dst):
            os.unlink(dst)
        os.link(src_path, dst)
        return {"shard": shard, "hardlinked": True, "s": round(time.time() - t0, 1)}

    fd_src = os.open(src_path, os.O_RDONLY)

    def src_bytes(name: str) -> bytes:
        a, b = sh[name]["data_offsets"]
        buf = os.pread(fd_src, b - a, sbase + a)
        if len(buf) != b - a:
            raise IOError(f"short read of {name} in {shard}")
        return buf

    tmp = dst + ".part"
    n_exp_scale = n_copied = n_patched = 0
    ok = False
    try:
        with open(tmp, "wb") as fo:
            fo.write(struct.pack("<Q", len(ref_raw)))
            fo.write(ref_raw)
            for name, meta in sorted(ref.items(), key=lambda kv: kv[1]["data_offsets"][0]):
                a, b = meta["data_offsets"]
                if fo.tell() != base + a:
                    raise ValueError(f"{shard}: gap before {name} ({fo.tell()} != {base + a})")
                if EXPERT_RE.match(name) and name.endswith(".scale"):
                    stem = name[: -len(".scale")]
                    ws = sh[stem + ".weight_scale"]
                    if ws["dtype"] != "F8_E4M3" or ws["shape"] != [meta["shape"][0], meta["shape"][1] * 2]:
                        raise ValueError(f"{name}: unexpected NVFP4 scale {ws['dtype']} {ws['shape']}")
                    data = nvfp4_scale_to_ue8m0(src_bytes(stem + ".weight_scale"), src_bytes(stem + ".weight_scale_2"), ws["shape"])
                    n_exp_scale += 1
                else:
                    sm = sh.get(name)
                    if sm is None:
                        raise KeyError(f"{name} missing from source {shard}")
                    if sm["shape"] != meta["shape"] or not (sm["dtype"] == meta["dtype"] or (EXPERT_RE.match(name) and {sm["dtype"], meta["dtype"]} == {"U8", "I8"})):
                        raise ValueError(f"{name}: source {sm['dtype']} {sm['shape']} vs reference {meta['dtype']} {meta['shape']}")
                    data = src_bytes(name)
                    if name in patch_sha:
                        if hashlib.sha256(data).hexdigest() != patch_sha[name]:
                            raise ValueError(f"{name}: sha256 does not match the patch manifest")
                        n_patched += 1
                    n_copied += 1
                if len(data) != b - a:
                    raise ValueError(f"{name}: {len(data)} bytes, reference span {b - a}")
                fo.write(data)
            if fo.tell() != size:
                raise ValueError(f"{shard}: wrote {fo.tell()} bytes, reference size {size}")
            fo.flush()
            os.fsync(fo.fileno())
            try:  # do not leave 7 GB of page cache behind per shard on a unified-memory box
                os.posix_fadvise(fo.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
                os.posix_fadvise(fd_src, 0, 0, os.POSIX_FADV_DONTNEED)
            except (AttributeError, OSError):
                pass
        os.replace(tmp, dst)
        ok = True
    finally:
        os.close(fd_src)
        if not ok and os.path.exists(tmp):
            os.unlink(tmp)
    return {"shard": shard, "expert_scales": n_exp_scale, "copied": n_copied, "patched_verified": n_patched,
            "bytes": size, "s": round(time.time() - t0, 1)}


# --------------------------------------------------------------------------- driver

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", required=True, help="NVFP4 checkpoint directory (48 shards + index)")
    ap.add_argument("--out", required=True, help="output directory (same filesystem as --src for hardlinks)")
    ap.add_argument("--ref-repo", default=REF_REPO)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", default="", help="comma-separated shard numbers, e.g. 3,13 (testing)")
    a = ap.parse_args(argv)

    os.makedirs(a.out, exist_ok=True)
    refs = fetch_reference_headers(os.path.join(a.out, ".reference-headers.json"), a.ref_repo)
    shards = sorted(refs)
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        shards = [s for s in shards if int(s[6:11]) in want]
    missing = [s for s in shards if not os.path.isfile(os.path.join(a.src, s))]
    if missing:
        print(f"source is missing {len(missing)} shards, first {missing[0]}", file=sys.stderr)
        return 2

    patch_sha = {}
    man = os.path.join(a.src, "uncensored_patch_manifest.json")
    if os.path.isfile(man):
        patch_sha = {k: v["source_sha256"] for k, v in json.load(open(man))["items"].items() if v.get("patched")}
        print(f"patch manifest: {len(patch_sha)} tensors will be checked against source_sha256")

    t0 = time.time()
    results, failed = [], []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(convert_shard, a.src, a.out, s, refs[s]["raw"], patch_sha): s for s in shards}
        for fu in as_completed(futs):
            s = futs[fu]
            try:
                r = fu.result()
                results.append(r)
                print(json.dumps(r), flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(s)
                print(f"FAILED {s}: {type(e).__name__}: {e}", flush=True)
    if failed:
        print(f"{len(failed)} shards failed: {failed}", file=sys.stderr)
        return 1

    if not a.only:
        # the index and the small files: the reference index layout, the reference config.json (the
        # source's carries an NVFP4 quantization_config this format no longer has), everything else
        # (tokenizer, encoding/, inference/, licences, the merge's provenance) from the source
        wm, total = {}, 0
        for s, r in refs.items():
            h = json.loads(r["raw"])
            h.pop("__metadata__", None)
            for k, v in h.items():
                wm[k] = s
                total += v["data_offsets"][1] - v["data_offsets"][0]
        json.dump({"metadata": {"total_size": total}, "weight_map": dict(sorted(wm.items()))},
                  open(os.path.join(a.out, "model.safetensors.index.json"), "w"), indent=2)
        cfg = _get(HF.format(repo=a.ref_repo, f="config.json"))
        open(os.path.join(a.out, "config.json"), "wb").write(cfg)
        for e in os.listdir(a.src):
            if e.endswith(".safetensors") or e in ("model.safetensors.index.json", "config.json") or e.startswith("."):
                continue
            p, q = os.path.join(a.src, e), os.path.join(a.out, e)
            if os.path.isdir(p):
                shutil.copytree(p, q, dirs_exist_ok=True)
            else:
                shutil.copy2(p, q)
    n_scale = sum(r.get("expert_scales", 0) for r in results)
    n_patch = sum(r.get("patched_verified", 0) for r in results)
    print(f"done: {len(results)} shards ({sum(1 for r in results if r.get('hardlinked'))} hardlinked, "
          f"{sum(1 for r in results if r.get('skipped'))} skipped), {n_scale} expert scales converted, "
          f"{n_patch} patched tensors verified, {time.time() - t0:.0f} s")
    if patch_sha and not a.only and n_patch != len(patch_sha) and not any(r.get("skipped") for r in results):
        print(f"WARNING: manifest lists {len(patch_sha)} patched tensors, {n_patch} were verified", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
