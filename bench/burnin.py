#!/usr/bin/env python3
"""
burnin.py -- N concurrent coding "agents" against one server for a fixed time.

The v41 server is single-sequence (requests queue on a lock), so this measures stability and the
queue a multi-agent client sees, not parallel throughput: per request the end-to-end latency (queue +
prefill + decode), the engine's own decode rate and NVMe traffic from x_engine_stats, and whether the
answer's Python code parses. A sampler records host memory and GPU state every 15 s.

  python3 bench/burnin.py --agents 5 --minutes 20 --out results/momonv/burnin-fp4.json
"""
import argparse, ast, json, os, re, statistics, subprocess, threading, time
from urllib import request as urlrequest

TASKS = [
    "Write a Python function that merges overlapping intervals. Include a short docstring.",
    "Write a Python LRU cache class with get and put in O(1), without functools.",
    "Write a Python function that parses a CSV line with quoted fields containing commas.",
    "Write a Python async function that fetches several URLs concurrently with a limit of 3 at a time using asyncio.Semaphore (assume an async fetch(url) exists).",
    "Write a Python function computing the Levenshtein distance of two strings with O(min(n,m)) memory.",
    "Write a Python class for a thread-safe bounded queue using threading.Condition.",
    "Write a Python function that topologically sorts a dependency dict and raises on cycles.",
    "Write a Python generator that yields sliding-window averages over an iterable of numbers.",
    "Write a Python function that validates an IPv4 address string without using the ipaddress module.",
    "Write a Python dataclass-based bank account with deposit, withdraw and a transaction history, raising on overdraft.",
]
SYSTEM = "You are a senior Python engineer. Answer with one Python code block and at most two sentences of explanation."


def post(base, body, timeout):
    req = urlrequest.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                             headers={"content-type": "application/json"})
    with urlrequest.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def code_ok(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if not blocks:
        return None
    try:
        ast.parse(blocks[0])
        return True
    except SyntaxError:
        return False


def agent(i, a, deadline, out, lock):
    n = 0
    while time.time() < deadline:
        task = TASKS[(i * 3 + n) % len(TASKS)]
        body = {"model": a.model, "max_tokens": a.max_tokens, "temperature": 0.6,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]}
        t0 = time.time()
        rec = {"agent": i, "seq": n, "task": TASKS.index(task), "start": t0}
        try:
            d = post(a.base, body, a.timeout)
            rec["latency_s"] = time.time() - t0
            if "error" in d:
                rec["error"] = str(d["error"])[:300]
            else:
                txt = d["choices"][0]["message"]["content"] or ""
                rec.update(tokens=d["usage"]["completion_tokens"], finish=d["choices"][0].get("finish_reason"),
                           code_ok=code_ok(txt), chars=len(txt), stats=d.get("x_engine_stats", {}))
                if a.save_dir:
                    with open(os.path.join(a.save_dir, f"a{i}-{n:03d}.md"), "w") as f:
                        f.write(f"# task {rec['task']}: {task}\n\n{txt}\n")
        except Exception as e:  # noqa: BLE001
            rec["latency_s"] = time.time() - t0
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        rec["end"] = time.time()
        with lock:
            out.append(rec)
            ok = "ERR" if "error" in rec else f"{rec['tokens']} tok, code {'ok' if rec['code_ok'] else rec['code_ok']}"
            print(f"[{time.strftime('%H:%M:%S')}] agent {i} #{n}: {rec['latency_s']:.0f}s, {ok}", flush=True)
        n += 1


def sampler(stop, samples, base):
    while not stop.is_set():
        s = {"t": time.time()}
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    s["mem_avail_gib"] = int(line.split()[1]) / 1048576
            q = subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,temperature.gpu,power.draw,utilization.gpu",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
            v = [x.strip() for x in q.split(",")]
            s.update(gpu_mhz=float(v[0]), gpu_c=float(v[1]), gpu_w=float(v[2]) if v[2] not in ("[N/A]", "") else None,
                     gpu_util=float(v[3]))
            h = json.loads(urlrequest.urlopen(base + "/health", timeout=10).read())
            s["server_ok"] = h.get("status") == "ok"
        except Exception as e:  # noqa: BLE001
            s["err"] = str(e)[:120]
        samples.append(s)
        stop.wait(15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:" + os.environ.get("PORT", "8001"))
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--agents", type=int, default=5)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--out", required=True)
    ap.add_argument("--save-dir", default=None)
    a = ap.parse_args()
    if a.save_dir:
        os.makedirs(a.save_dir, exist_ok=True)
    out, samples, lock, stop = [], [], threading.Lock(), threading.Event()
    t0 = time.time()
    deadline = t0 + a.minutes * 60
    st = threading.Thread(target=sampler, args=(stop, samples, a.base), daemon=True)
    st.start()
    ths = [threading.Thread(target=agent, args=(i, a, deadline, out, lock)) for i in range(a.agents)]
    for t in ths:
        t.start()
        time.sleep(0.5)
    for t in ths:
        t.join()
    stop.set()
    st.join(timeout=20)
    wall = time.time() - t0

    ok = [r for r in out if "error" not in r]
    tok = sum(r["tokens"] for r in ok)
    eng_dec = [r["stats"].get("decode_tok_s") for r in ok if r["stats"].get("decode_tok_s")]
    lat = [r["latency_s"] for r in ok]
    nvme = sum(r["stats"].get("nvme_gb", 0) or 0 for r in ok)
    parsed = [r["code_ok"] for r in ok if r["code_ok"] is not None]
    summ = {
        "agents": a.agents, "minutes_target": a.minutes, "wall_s": round(wall, 1),
        "requests": len(out), "ok": len(ok), "errors": len(out) - len(ok),
        "completion_tokens": tok, "aggregate_tok_s": round(tok / wall, 3),
        "engine_decode_tok_s_median": round(statistics.median(eng_dec), 3) if eng_dec else None,
        "latency_s_median": round(statistics.median(lat), 1) if lat else None,
        "latency_s_max": round(max(lat), 1) if lat else None,
        "finish_length": sum(1 for r in ok if r.get("finish") == "length"),
        "code_blocks": len(parsed), "code_parses": sum(parsed),
        "nvme_gb_total": round(nvme, 1),
        "mem_avail_gib_min": round(min(s["mem_avail_gib"] for s in samples if "mem_avail_gib" in s), 1) if samples else None,
        "gpu_mhz_median": statistics.median([s["gpu_mhz"] for s in samples if "gpu_mhz" in s]) if samples else None,
        "gpu_c_max": max((s["gpu_c"] for s in samples if "gpu_c" in s), default=None),
        "server_health_failures": sum(1 for s in samples if s.get("server_ok") is False or "err" in s),
    }
    json.dump({"summary": summ, "requests": out, "samples": samples}, open(a.out, "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
