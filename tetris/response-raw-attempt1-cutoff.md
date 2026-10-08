```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tetris — Guideline</title>
    <style>
        * {
            box-sizing: border-box;
            user-select: none;
        }
        body {
            margin: 0;
            min-height: 100vh;
            background: #0b0e14;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Segoe UI', 'Courier New', monospace;
            color: #e0e6f0;
        }
        .game-container {
            display: flex;
            gap: 20px;
            padding: 20px;
            background: #12161f;
            border-radius: 16px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.7);
            border: 1px solid #2a3140;
        }
        .side-panel {
            display: flex;
            flex-direction: column;
            gap: 16px;
            width: 140px;
        }
        .panel-box {
            background: #1a1f2b;
            border-radius: 10px;
            padding: 10px 12px;
            border: 1px solid #2e3648;
        }
        .panel-box h3 {
            margin: 0 0 6px 0;
            font-size: 11px;
            letter-spacing: 1.5px;
            color: #7a8aa8;
            text-transform: uppercase;
            font-weight: 600;
        }
        .panel-box .value {
            font-size: 22px;
            font-weight: 700;
            color: #d0e0ff;
            font-variant-numeric: tabular-nums;
        }
        .panel-box .value.small {
            font-size: 16px;
        }
        canvas {
            display: block;
            border-radius: 8px;
            background: #0a0d13;
            box-shadow: inset 0 0 0 1px #2a3140;
        }
        #boardCanvas {
            width: 300px;
            height: 600px;
        }
        #holdCanvas, #nextCanvas {
            width: 100%;
            height: auto;
            background: #0a0d13;
            border-radius: 6px;
        }
        .controls-legend {
            font-size: 10px;
            line-height: 1.6;
            color: #8a9bb8;
        }
        .controls-legend span {
            color: #c0d0e8;
            font-weight: 600;
        }
        .overlay {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: rgba(8, 11, 18, 0.88);
            border-radius: 8px;
            z-index: 10;
            text-align: center;
            padding: 20px;
            backdrop-filter: blur(3px);
        }
        .overlay h1 {
            font-size: 28px;
            margin: 0 0 10px 0;
            color: #a0c0ff;
            letter-spacing: 3px;
        }
        .overlay p {
            margin: 6px 0;
            font-size: 14px;
            color: #b0c0d8;
        }
        .overlay .big-score {
            font-size: 32px;
            font-weight: 800;
            color: #ffd966;
            margin: 10px 0;
        }
        .board-wrapper {
            position: relative;
            width: 300px;
            height: 600px;
        }
        .action-label {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 16px;
            font-weight: 700;
            color: #ffd966;
            text-shadow: 0 0 12px rgba(255,217,102,0.5);
            letter-spacing: 2px;
            pointer-events: none;
            white-space: nowrap;
            z-index: 5;
        }
        .next-queue {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .next-piece {
            display: flex;
            justify-content: center;
        }
        .next-piece canvas {
            width: 100%;
            height: auto;
        }
    </style>
</head>
<body>
<div class="game-container">
    <div class="side-panel">
        <div class="panel-box">
            <h3>Hold</h3>
            <canvas id="holdCanvas" width="120" height="80"></canvas>
        </div>
        <div class="panel-box">
            <h3>Score</h3>
            <div class="value" id="scoreDisplay">0</div>
        </div>
        <div class="panel-box">
            <h3>Level</h3>
            <div class="value" id="levelDisplay">1</div>
        </div>
        <div class="panel-box">
            <h3>Lines</h3>
            <div class="value" id="linesDisplay">0</div>
        </div>
        <div class="panel-box">
            <h3>High Score</h3>
            <div class="value small" id="highScoreDisplay">0</div>
        </div>
    </div>

    <div class="board-wrapper">
        <canvas id="boardCanvas" width="300" height="600"></canvas>
        <div class="action-label" id="actionLabel"></div>
        <div class="overlay" id="overlay">
            <h1 id="overlayTitle">TETRIS</h1>
            <p id="overlayText">Press Enter to start</p>
            <p id="overlaySub"></p>
        </div>
    </div>

    <div class="side-panel">
        <div class="panel-box">
            <h3>Next</h3>
            <div class="next-queue" id="nextQueue"></div>
        </div>
        <div class="panel-box controls-legend">
            <h3>Controls</h3>
            <div>← → <span>Move</span></div>
            <div>↓ <span>Soft drop</span></div>
            <div>Space <span>Hard drop</span></div>
            <div>↑ / X <span>Rotate CW</span></div>
            <div>Z / Ctrl <span>Rotate CCW</span></div>
            <div>C / Shift <span>Hold</span></div>
            <div>P / Esc <span>Pause</span></div>
            <div>R <span>Restart</span></div>
        </div>
    </div>
</div>

<script>
    (function() {
        // ---------- CONSTANTS ----------
        const COLS = 10;
        const VISIBLE_ROWS = 20;
        const HIDDEN_ROWS = 2;
        const TOTAL_ROWS = VISIBLE_ROWS + HIDDEN_ROWS;
        const CELL_SIZE = 30;

        const COLORS = {
            I: '#00f0f0',
            O: '#f0f000',
            T: '#a000f0',
            S: '#00f000',
            Z: '#f00000',
            J: '#0000f0',
            L: '#f0a000',
            ghost: 'rgba(200, 220, 255, 0.25)',
            grid: '#1a1f2b',
            border: '#2a3140'
        };

        // Tetromino shapes (4x4 for I, 3x3 for others, but we use 4x4 for all for simplicity)
        const SHAPES = {
            I: [
                [0,0,0,0],
                [1,1,1,1],
                [0,0,0,0],
                [0,0,0,0]
            ],
            O: [
                [0,0,0,0],
                [0,1,1,0],
                [0,1,1,0],
                [0,0,0,0]
            ],
            T: [
                [0,0,0,0],
                [0,1,0,0],
                [1,1,1,0],
                [0,0,0,0]
            ],
            S: [
                [0,0,0,0],
                [0,1,1,0],
                [1,1,0,0],
                [0,0,0,0]
            ],
            Z: [
                [0,0,0,0],
                [1,1,0,0],
                [0,1,1,0],
                [0,0,0,0]
            ],
            J: [
                [0,0,0,0],
                [1,0