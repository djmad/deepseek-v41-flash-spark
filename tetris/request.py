#!/usr/bin/env python3
"""Ask the local DeepSeek-V4.1-Flash server for a single-file Tetris and stream the answer to disk."""
import json, re, sys, time
from urllib import request as urlrequest

BASE = "http://127.0.0.1:8001"
SPEC = """Write a complete, playable Tetris game as ONE self-contained HTML file (HTML + CSS + JavaScript inline,
no external libraries, no network requests). Follow the official Tetris Guideline:

PLAYFIELD & PIECES
- 10 columns x 20 visible rows, plus 2 hidden rows above where pieces spawn.
- 7 tetrominoes with guideline colors: I cyan, O yellow, T purple, S green, Z red, J blue, L orange.
- Pieces spawn horizontally, centered (I and O in the middle columns), J L S T Z flat side down.
- 7-bag randomizer (shuffle all 7, deal them, repeat).

ROTATION (SRS)
- Super Rotation System with the full wall-kick tables: the JLSTZ table and the separate I table,
  5 tests per rotation, clockwise and counter-clockwise. The O piece does not kick.

CONTROLS (keyboard)
- Left/Right: move, with DAS 167 ms and ARR 33 ms.
- Down: soft drop (20x gravity, 1 point per cell). Space: hard drop (2 points per cell, locks immediately).
- Up or X: rotate clockwise. Z or Ctrl: rotate counter-clockwise.
- C or Shift: hold (swap with hold slot, only once per piece until it locks; held piece resets to spawn orientation).
- P or Escape: pause/resume. R: restart after game over.

GAMEPLAY
- Ghost piece showing where the piece will land.
- Next queue showing the next 5 pieces. Hold box.
- Lock delay 500 ms; moving or rotating resets it, at most 15 resets per piece.
- Gravity per level: seconds per row = (0.8 - (level - 1) * 0.007) ^ (level - 1).
- Start at level 1; level up every 10 cleared lines.
- Game over on block out (new piece overlaps) or lock out (piece locks fully above the visible field).

SCORING (multiply by current level unless noted)
- Single 100, Double 300, Triple 500, Tetris 800.
- T-Spin (3-corner rule): T-Spin no lines 400, Single 800, Double 1200, Triple 1600;
  T-Spin Mini no lines 100, Mini Single 200.
- Back-to-Back: consecutive "difficult" clears (Tetris or any T-Spin line clear) get x1.5.
- Combo: +50 x combo count x level for each consecutive line-clearing piece.
- Perfect clear (board empty after a clear): +3500 x level.
- Show score, level, lines, and a short action label (e.g. "TETRIS", "T-SPIN DOUBLE", "B2B", "COMBO x3").
- Keep the high score in localStorage.

PRESENTATION
- Draw with <canvas>. Dark background, clear grid, blocks with a subtle bevel.
- Side panels for hold, next queue, score, level, lines, high score, and a controls legend.
- Start screen ("Press Enter to start"), pause overlay, game-over overlay with final score.
- Use requestAnimationFrame for the game loop with delta time.

Output ONLY the complete HTML file in a single ```html code block. Make sure the code is complete
and runs without errors; do not leave any function unimplemented."""


def main(out_raw, max_tokens):
    body = {"model": "deepseek-v4.1-flash", "stream": True, "max_tokens": max_tokens, "temperature": 0.3,
            "messages": [{"role": "user", "content": SPEC}]}
    req = urlrequest.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                             headers={"content-type": "application/json"})
    t0 = time.time(); n = 0; text = []; last = t0; stats = None; usage = None
    with urlrequest.urlopen(req, timeout=7200) as r, open(out_raw, "w") as f:
        for line in r:
            line = line.decode().strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            d = json.loads(line[5:])
            stats = d.get("x_engine_stats", stats); usage = d.get("usage", usage)
            for ch in d.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if c:
                    text.append(c); f.write(c); f.flush(); n += 1
            if time.time() - last > 60:
                last = time.time()
                print(f"[{time.strftime('%H:%M:%S')}] {len(''.join(text))} chars after {time.time() - t0:.0f}s", flush=True)
    full = "".join(text)
    m = re.search(r"```html\s*\n(.*?)```", full, re.S) or re.search(r"(<!DOCTYPE html.*</html>)", full, re.S | re.I)
    print(json.dumps({"seconds": round(time.time() - t0, 1), "chars": len(full), "usage": usage,
                      "decode_tok_s": (stats or {}).get("decode_tok_s"), "accept_len": (stats or {}).get("accept_len_mean"),
                      "html_found": bool(m)}), flush=True)
    if m:
        open(sys.argv[3], "w").write(m.group(1).strip() + "\n")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
