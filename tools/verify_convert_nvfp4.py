"""
verify_convert_nvfp4.py -- check a converted checkpoint (tools/convert_nvfp4.py) against the reference
deepseek-ai/DeepSeek-V4.1-Flash on Hugging Face, by HTTP range request: no reference shard is
downloaded, only the tensors sampled (about 19 MB per expert).

  * routed experts, sampled across all layers: the dequantized values must be identical (the codes may
    differ only where the reference wrote a zero as -0) and the UE8M0 scales byte-identical;
  * non-expert tensors, sampled: byte-identical to the reference, except the tensors a merge's
    `uncensored_patch_manifest.json` lists, which must match its `source_sha256` and differ from the
    reference (`original_sha256`).

  python tools/verify_convert_nvfp4.py --model-dir deepseek-v41-uncensored/native --experts 24 --dense 24
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_nvfp4 import EXPERT_RE, HF, REF_REPO, _get, read_header  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--experts", type=int, default=24, help="routed experts to sample (x3 projections)")
    ap.add_argument("--dense", type=int, default=24, help="non-expert tensors to sample")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    import torch

    md = a.model_dir
    wm = json.load(open(os.path.join(md, "model.safetensors.index.json")))["weight_map"]
    # sample only what is on disk (a partial conversion can be checked while the rest downloads)
    have = {f for f in set(wm.values()) if os.path.isfile(os.path.join(md, f))}
    wm = {k: f for k, f in wm.items() if f in have}
    print(f"checking {len(have)} of 48 shards")
    man = os.path.join(md, "uncensored_patch_manifest.json")
    patched = json.load(open(man))["items"] if os.path.isfile(man) else {}
    rng = random.Random(a.seed)
    hdrs, ref_hdrs = {}, {}

    def local(name):
        f = wm[name]
        if f not in hdrs:
            hdrs[f] = read_header(os.path.join(md, f))
        base, h = hdrs[f]
        s, e = h[name]["data_offsets"]
        with open(os.path.join(md, f), "rb") as fh:
            fh.seek(base + s)
            return fh.read(e - s)

    def ref(name):
        f = wm[name]
        url = HF.format(repo=REF_REPO, f=f)
        if f not in ref_hdrs:
            n = struct.unpack("<Q", _get(url, 0, 8))[0]
            h = json.loads(_get(url, 8, 8 + n))
            h.pop("__metadata__", None)
            ref_hdrs[f] = (8 + n, h)
        base, h = ref_hdrs[f]
        s, e = h[name]["data_offsets"]
        return _get(url, base + s, base + e)

    FP4 = torch.tensor([0.0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6])

    def codes(b):
        t = torch.frombuffer(bytearray(b), dtype=torch.uint8)
        return torch.stack([t & 15, t >> 4], -1).flatten().long()

    fails = 0
    layers = sorted({int(k.split(".")[1]) for k in wm if EXPERT_RE.match(k)})
    n_exp = max(int(k.split(".")[4]) for k in wm if EXPERT_RE.match(k)) + 1
    for i in range(a.experts):
        L = layers[i % len(layers)] if a.experts >= len(layers) else rng.choice(layers)
        E = rng.randrange(n_exp)
        for w in ("w1", "w2", "w3"):
            p = f"layers.{L}.ffn.experts.{E}.{w}"
            lw, rw = local(p + ".weight"), ref(p + ".weight")
            ls, rs = local(p + ".scale"), ref(p + ".scale")
            cl, cr = codes(lw), codes(rw)
            diff = cl != cr
            only_zero_sign = bool(((cr[diff] == 8) & (cl[diff] == 0)).all())
            vals = bool(torch.equal(FP4[cl], FP4[cr]))
            ok = ls == rs and vals and only_zero_sign
            fails += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {p}: scales {'identical' if ls == rs else 'DIFFER'}, values "
                  f"{'identical' if vals else 'DIFFER'}, {int(diff.sum())} codes differ "
                  f"({'all -0 -> +0' if only_zero_sign else 'NOT only zero sign'})", flush=True)

    dense = [k for k in wm if not EXPERT_RE.match(k) and not re.search(r"\.engram\.", k)]
    pick = [k for k in patched if k in wm][:4] + rng.sample(dense, min(a.dense, len(dense)))
    for name in pick:
        lb = local(name)
        sha = hashlib.sha256(lb).hexdigest()
        if name in patched:
            ok = sha == patched[name]["source_sha256"] and sha != patched[name]["original_sha256"]
            what = "matches the uncensored source, differs from the reference"
        else:
            ok = lb == ref(name)
            what = "identical to the reference"
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {what if ok else 'MISMATCH'} ({len(lb)} B)", flush=True)

    print()
    print(f"{fails} failed" if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
