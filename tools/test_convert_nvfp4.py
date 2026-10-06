"""Checks on the NVFP4 -> native converter, on a synthetic two-expert shard: no GPU, no checkpoint.

The fake source is built the way NVIDIA's conversion is: MXFP4 codes with -0 written as +0, each
UE8M0 scale split into two equal E4M3 scales over a power-of-two weight_scale_2. The converter must
hand back the reference header byte for byte and the same values, and refuse a scale it cannot map.

Run: python3 tools/test_convert_nvfp4.py
"""
import hashlib
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import torch  # noqa: E402

import convert_nvfp4 as C  # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    show = (lambda v: f"<{len(v)} bytes>" if isinstance(v, bytes) else v)
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {show(got)} (want {show(want)})")
    if not ok:
        fails.append(name)


def st_bytes(tensors, order):
    """safetensors bytes for {name: (dtype, shape, bytes)} laid out in `order`."""
    hdr, off = {}, 0
    for n in order:
        dt, sh, b = tensors[n]
        hdr[n] = {"dtype": dt, "shape": sh, "data_offsets": [off, off + len(b)]}
        off += len(b)
    raw = json.dumps(hdr, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 8)
    return raw, struct.pack("<Q", len(raw)) + raw + b"".join(tensors[n][2] for n in order)


g = torch.Generator().manual_seed(0)
N, K = 8, 64
FP4 = torch.tensor([0.0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6])
ref_t, src_t = {}, {}
for e in range(2):
    for w in ("w1", "w2", "w3"):
        p = f"layers.0.ffn.experts.{e}.{w}"
        codes = torch.randint(0, 16, (N, K), generator=g, dtype=torch.uint8)
        packed = (codes[:, 0::2] | (codes[:, 1::2] << 4)).contiguous()
        ue8 = torch.randint(106, 122, (N, K // 32), generator=g, dtype=torch.uint8)
        if e == 1 and w == "w2":
            ue8[0, 0] = 105  # 2^-9 x 2^-13: the smallest E4M3 subnormal still maps exactly
        ref_t[p + ".weight"] = ("I8", [N, K // 2], packed.numpy().tobytes())
        ref_t[p + ".scale"] = ("F8_E8M0", [N, K // 32], ue8.numpy().tobytes())
        # NVIDIA's form: -0 -> +0, scale per 16 = 2^(b-127) / gs as E4M3, gs a power of two
        nv_codes = torch.where(codes == 8, torch.zeros_like(codes), codes)
        nv_packed = (nv_codes[:, 0::2] | (nv_codes[:, 1::2] << 4)).contiguous()
        gs = 2.0 ** -13
        s16 = (torch.exp2(ue8.double() - 127) / gs).repeat_interleave(2, 1).float().to(torch.float8_e4m3fn)
        src_t[p + ".weight"] = ("U8", [N, K // 2], nv_packed.numpy().tobytes())
        src_t[p + ".weight_scale"] = ("F8_E4M3", [N, K // 16], s16.view(torch.uint8).numpy().tobytes())
        src_t[p + ".weight_scale_2"] = ("F32", [], struct.pack("<f", gs))
        src_t[p + ".input_scale"] = ("F32", [], struct.pack("<f", 0.001))
ref_t["layers.0.attn.wo_b.weight"] = ("F8_E4M3", [4, 4], bytes(range(16)))
src_t["layers.0.attn.wo_b.weight"] = ("F8_E4M3", [4, 4], bytes(range(16, 32)))  # a "patched" tensor

# the reference keeps scales in front of weights (as deepseek-ai's shards do); the source does not
ref_order = sorted(ref_t, key=lambda n: (not n.endswith(".scale"), n))
ref_raw, _ = st_bytes(ref_t, ref_order)
_, src_file = st_bytes(src_t, sorted(src_t))

with tempfile.TemporaryDirectory() as d:
    src, out = os.path.join(d, "src"), os.path.join(d, "out")
    os.makedirs(src), os.makedirs(out)
    shard = "model-00003-of-00048.safetensors"
    open(os.path.join(src, shard), "wb").write(src_file)
    patch = {"layers.0.attn.wo_b.weight": hashlib.sha256(bytes(range(16, 32))).hexdigest()}
    r = C.convert_shard(src, out, shard, ref_raw, patch)
    check("expert scales converted", r.get("expert_scales"), 6)
    check("patched tensor verified", r.get("patched_verified"), 1)
    data = open(os.path.join(out, shard), "rb").read()
    n = struct.unpack("<Q", data[:8])[0]
    check("header is the reference's, byte for byte", data[8:8 + n], ref_raw)
    hdr = json.loads(data[8:8 + n])
    base = 8 + n

    def tensor(name):
        a, b = hdr[name]["data_offsets"]
        return data[base + a: base + b]

    for name, (dt, sh, b) in ref_t.items():
        got = tensor(name)
        if name.endswith(".scale"):
            check(f"{name} UE8M0 identical", got, b)
        elif ".experts." in name:
            # values equal; codes equal except the source's -0 that NVIDIA stored as +0
            dec = lambda x: FP4[torch.stack([torch.frombuffer(bytearray(x), dtype=torch.uint8) & 15,  # noqa: E731
                                             torch.frombuffer(bytearray(x), dtype=torch.uint8) >> 4], -1).flatten().long()]
            check(f"{name} values identical", bool(torch.equal(dec(got), dec(b))), True)
        else:
            check(f"{name} copied from source", got, src_t[name][2])

    # a wrong manifest hash must stop the shard
    os.unlink(os.path.join(out, shard))
    try:
        C.convert_shard(src, out, shard, ref_raw, {"layers.0.attn.wo_b.weight": "0" * 64})
        check("bad manifest hash refused", False, True)
    except ValueError:
        check("bad manifest hash refused", True, True)
    check("no output left behind on failure", sorted(os.listdir(out)), [])

# a scale that is not a power of two, or a pair that differs, is refused
gs = struct.pack("<f", 2.0 ** -13)
bad = torch.tensor([[3.0, 3.0]]).to(torch.float8_e4m3fn).view(torch.uint8).numpy().tobytes()
try:
    C.nvfp4_scale_to_ue8m0(bad, gs, [1, 2])
    check("non power of two refused", False, True)
except ValueError:
    check("non power of two refused", True, True)
pair = torch.tensor([[2.0, 4.0]]).to(torch.float8_e4m3fn).view(torch.uint8).numpy().tobytes()
try:
    C.nvfp4_scale_to_ue8m0(pair, gs, [1, 2])
    check("unequal pair refused", False, True)
except ValueError:
    check("unequal pair refused", True, True)

print()
print(f"{len(fails)} failed" if fails else "all checks passed")
sys.exit(1 if fails else 0)
