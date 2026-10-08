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
            background: #141a24;
            border-radius: 16px;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.8);
            border: 1px solid #2a3442;
        }
        .side-panel {
            display: flex;
            flex-direction: column;
            gap: 12px;
            width: 140px;
        }
        .panel-box {
            background: #0f141c;
            border: 1px solid #2a3442;
            border-radius: 8px;
            padding: 10px;
        }
        .panel-box h3 {
            margin: 0 0 6px 0;
            font-size: 12px;
            letter-spacing: 2px;
            color: #7a8ba0;
            text-transform: uppercase;
            font-weight: 600;
        }
        .panel-box .value {
            font-size: 22px;
            font-weight: 700;
            color: #d0e0ff;
            font-variant-numeric: tabular-nums;
        }
        .mini-canvas {
            display: block;
            margin: 0 auto;
            background: #0a0d12;
            border-radius: 4px;
        }
        .controls-legend {
            font-size: 11px;
            line-height: 1.6;
            color: #8a9bb0;
        }
        .controls-legend span {
            color: #c0d0e0;
            font-weight: 600;
        }
        canvas#board {
            display: block;
            background: #0a0d12;
            border-radius: 6px;
            border: 2px solid #2a3442;
        }
        .overlay {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: rgba(5, 8, 14, 0.88);
            border-radius: 6px;
            z-index: 10;
            text-align: center;
            padding: 20px;
        }
        .overlay h1 {
            font-size: 28px;
            margin: 0 0 10px 0;
            color: #7ec8ff;
            letter-spacing: 3px;
        }
        .overlay p {
            margin: 4px 0;
            font-size: 14px;
            color: #a0b4cc;
        }
        .overlay .big {
            font-size: 20px;
            color: #ffd966;
            font-weight: 700;
        }
        .board-wrapper {
            position: relative;
        }
        .action-label {
            position: absolute;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 16px;
            font-weight: 700;
            color: #ffd966;
            text-shadow: 0 0 12px rgba(255, 217, 102, 0.5);
            letter-spacing: 2px;
            pointer-events: none;
            white-space: nowrap;
            z-index: 5;
        }
        .hidden {
            display: none !important;
        }
    </style>
</head>
<body>
<div class="game-container">
    <div class="side-panel">
        <div class="panel-box">
            <h3>Hold</h3>
            <canvas id="holdCanvas" class="mini-canvas" width="120" height="80"></canvas>
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
            <div class="value" id="highScoreDisplay">0</div>
        </div>
    </div>

    <div class="board-wrapper">
        <canvas id="board" width="300" height="600"></canvas>
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
            <canvas id="nextCanvas" class="mini-canvas" width="120" height="260"></canvas>
        </div>
        <div class="panel-box">
            <h3>Controls</h3>
            <div class="controls-legend">
                <span>← →</span> Move<br>
                <span>↓</span> Soft drop<br>
                <span>Space</span> Hard drop<br>
                <span>↑ / X</span> Rotate CW<br>
                <span>Z / Ctrl</span> Rotate CCW<br>
                <span>C / Shift</span> Hold<br>
                <span>P / Esc</span> Pause<br>
                <span>R</span> Restart
            </div>
        </div>
    </div>
</div>

<script>
    (function() {
        'use strict';

        // ---------- CONSTANTS ----------
        const COLS = 10;
        const ROWS = 20;
        const HIDDEN_ROWS = 2;
        const TOTAL_ROWS = ROWS + HIDDEN_ROWS;
        const CELL_SIZE = 30;

        const COLORS = {
            I: '#00f0f0',
            O: '#f0f000',
            T: '#a000f0',
            S: '#00f000',
            Z: '#f00000',
            J: '#0000f0',
            L: '#f0a000'
        };

        const SHAPES = {
            I: [
                [0,0,0,0],
                [1,1,1,1],
                [0,0,0,0],
                [0,0,0,0]
            ],
            O: [
                [1,1],
                [1,1]
            ],
            T: [
                [0,1,0],
                [1,1,1],
                [0,0,0]
            ],
            S: [
                [0,1,1],
                [1,1,0],
                [0,0,0]
            ],
            Z: [
                [1,1,0],
                [0,1,1],
                [0,0,0]
            ],
            J: [
                [1,0,0],
                [1,1,1],
                [0,0,0]
            ],
            L: [
                [0,0,1],
                [1,1,1],
                [0,0,0]
            ]
        };

        // SRS wall kick tables
        const KICKS_JLSTZ = {
            '0->1': [[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]],
            '1->0': [[0,0],[1,0],[1,-1],[0,2],[1,2]],
            '1->2': [[0,0],[1,0],[1,-1],[0,2],[1,2]],
            '2->1': [[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]],
            '2->3': [[0,0],[1,0],[1,1],[0,-2],[1,-2]],
            '3->2': [[0,0],[-1,0],[-1,-1],[0,2],[-1,2]],
            '3->0': [[0,0],[-1,0],[-1,-1],[0,2],[-1,2]],
            '0->3': [[0,0],[1,0],[1,1],[0,-2],[1,-2]]
        };

        const KICKS_I = {
            '0->1': [[0,0],[-2,0],[1,0],[-2,-1],[1,2]],
            '1->0': [[0,0],[2,0],[-1,0],[2,1],[-1,-2]],
            '1->2': [[0,0],[-1,0],[2,0],[-1,2],[2,-1]],
            '2->1': [[0,0],[1,0],[-2,0],[1,-2],[-2,1]],
            '2->3': [[0,0],[2,0],[-1,0],[2,1],[-1,-2]],
            '3->2': [[0,0],[-2,0],[1,0],[-2,-1],[1,2]],
            '3->0': [[0,0],[1,0],[-2,0],[1,-2],[-2,1]],
            '0->3': [[0,0],[-1,0],[2,0],[-1,2],[2,-1]]
        };

        // ---------- DOM ----------
        const boardCanvas = document.getElementById('board');
        const boardCtx = boardCanvas.getContext('2d');
        const holdCanvas = document.getElementById('holdCanvas');
        const holdCtx = holdCanvas.getContext('2d');
        const nextCanvas = document.getElementById('nextCanvas');
        const nextCtx = nextCanvas.getContext('2d');
        const scoreDisplay = document.getElementById('scoreDisplay');
        const levelDisplay = document.getElementById('levelDisplay');
        const linesDisplay = document.getElementById('linesDisplay');
        const highScoreDisplay = document.getElementById('highScoreDisplay');
        const actionLabel = document.getElementById('actionLabel');
        const overlay = document.getElementById('overlay');
        const overlayTitle = document.getElementById('overlayTitle');
        const overlayText = document.getElementById('overlayText');
        const overlaySub = document.getElementById('overlaySub');

        // ---------- GAME STATE ----------
        let board = [];
        let currentPiece = null;
        let holdPiece = null;
        let canHold = true;
        let nextQueue = [];
        let bag = [];
        let score = 0;
        let level = 1;
        let lines = 0;
        let highScore = parseInt(localStorage.getItem('tetrisHighScore') || '0', 10);
        let gameState = 'start'; // start, playing, paused, gameover
        let gravityTimer = 0;
        let lockTimer = 0;
        let lockResets = 0;
        let isLocking = false;
        let lastTime = 0;
        let rafId = null;
        let actionText = '';
        let actionTimer = 0;
        let combo = 0;
        let backToBack = false;
        let lastClearWasDifficult = false;

        // DAS/ARR
        let dasTimer = 0;
        let arrTimer = 0;
        let dasDirection = 0;
        const DAS_DELAY = 167;
        const ARR_DELAY = 33;

        // Soft drop
        let softDropActive = false;

        // ---------- INIT ----------
        function initBoard() {
            board = [];
            for (let r = 0; r < TOTAL_ROWS; r++) {
                board.push(new Array(COLS).fill(null));
            }
        }

        function resetGame() {
            initBoard();
            currentPiece = null;
            holdPiece = null;
            canHold = true;
            nextQueue = [];
            bag = [];
            score = 0;
            level = 1;
            lines = 0;
            gravityTimer = 0;
            lockTimer = 0;
            lockResets = 0;
            isLocking = false;
            combo = 0;
            backToBack = false;
            lastClearWasDifficult = false;
            actionText = '';
            actionTimer = 0;
            softDropActive = false;
            dasTimer = 0;
            arrTimer = 0;
            dasDirection = 0;
            fillBag();
            for (let i = 0; i < 5; i++) {
                nextQueue.push(getNextFromBag());
            }
            spawnPiece();
            updateUI();
        }

        function fillBag() {
            const pieces = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];
            for (let i = pieces.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [pieces[i], pieces[j]] = [pieces[j], pieces[i]];
            }
            bag = pieces;
        }

        function getNextFromBag() {
            if (bag.length === 0) fillBag();
            return bag.pop();
        }

        function createPiece(type) {
            const shape = SHAPES[type].map(row => row.slice());
            return {
                type: type,
                shape: shape,
                rotation: 0,
                x: 0,
                y: 0
            };
        }

        function spawnPiece() {
            const type = nextQueue.shift();
            nextQueue.push(getNextFromBag());
            const piece = createPiece(type);
            const shape = piece.shape;
            const w = shape[0].length;
            piece.x = Math.floor((COLS - w) / 2);
            // Spawn in hidden rows: top of piece at row 0 (which is hidden)
            piece.y = 0;
            // For pieces with empty top row, shift up
            if (type === 'I' || type === 'O') {
                piece.y = 0;
            } else {
                // J L S T Z have empty top row in their 3x3, so shift up by 1
                piece.y = -1;
            }
            currentPiece = piece;
            canHold = true;
            lockTimer = 0;
            lockResets = 0;
            isLocking = false;
            gravityTimer = 0;

            // Check block out
            if (collides(piece.shape, piece.x, piece.y)) {
                gameOver();
            }
        }

        // ---------- COLLISION ----------
        function collides(shape, px, py) {
            for (let r = 0; r < shape.length; r++) {
                for (let c = 0; c < shape[r].length; c++) {
                    if (shape[r][c]) {
                        const boardX = px + c;
                        const boardY = py + r;
                        if (boardX < 0 || boardX >= COLS || boardY >= TOTAL_ROWS) return true;
                        if (boardY >= 0 && board[boardY][boardX]) return true;
                    }
                }
            }
            return false;
        }

        // ---------- ROTATION ----------
        function rotatePiece(dir) {
            if (!currentPiece) return;
            const piece = currentPiece;
            if (piece.type === 'O') {
                piece.rotation = (piece.rotation + (dir === 'cw' ? 1 : 3)) % 4;
                return;
            }

            const oldRotation = piece.rotation;
            const newRotation = (oldRotation + (dir === 'cw' ? 1 : 3)) % 4;

            // Rotate shape matrix
            const oldShape = piece.shape;
            const n = oldShape.length;
            const newShape = [];
            for (let r = 0; r < n; r++) {
                newShape.push(new Array(n).fill(0));
            }
            for (let r = 0; r < n; r++) {
                for (let c = 0; c < n; c++) {
                    if (dir === 'cw') {
                        newShape[c][n - 1 - r] = oldShape[r][c];
                    } else {
                        newShape[n - 1 - c][r] = oldShape[r][c];
                    }
                }
            }

            const kickKey = oldRotation + '->' + newRotation;
            const kicks = piece.type === 'I' ? KICKS_I[kickKey] : KICKS_JLSTZ[kickKey];

            if (!kicks) return;

            for (const [dx, dy] of kicks) {
                const newX = piece.x + dx;
                const newY = piece.y + dy;
                if (!collides(newShape, newX, newY)) {
                    piece.shape = newShape;
                    piece.x = newX;
                    piece.y = newY;
                    piece.rotation = newRotation;
                    resetLockDelay();
                    return;
                }
            }
        }

        function resetLockDelay() {
            if (isLocking && lockResets < 15) {
                lockTimer = 0;
                lockResets++;
            }
        }

        // ---------- MOVEMENT ----------
        function movePiece(dx, dy) {
            if (!currentPiece) return false;
            const piece = currentPiece;
            if (!collides(piece.shape, piece.x + dx, piece.y + dy)) {
                piece.x += dx;
                piece.y += dy;
                if (dx !== 0) resetLockDelay();
                return true;
            }
            return false;
        }

        function hardDrop() {
            if (!currentPiece) return;
            let cells = 0;
            while (movePiece(0, 1)) {
                cells++;
            }
            score += cells * 2;
            lockPiece();
        }

        function softDrop() {
            if (!currentPiece) return;
            if (movePiece(0, 1)) {
                score += 1;
                gravityTimer = 0;
            }
        }

        function holdPieceAction() {
            if (!currentPiece || !canHold) return;
            const currentType = currentPiece.type;
            if (holdPiece === null) {
                holdPiece = currentType;
                spawnPiece();
            } else {
                const temp = holdPiece;
                holdPiece = currentType;
                const piece = createPiece(temp);
                const shape = piece.shape;
                const w = shape[0].length;
                piece.x = Math.floor((COLS - w) / 2);
                piece.y = (temp === 'I' || temp === 'O') ? 0 : -1;
                currentPiece = piece;
                lockTimer = 0;
                lockResets = 0;
                isLocking = false;
                gravityTimer = 0;
                if (collides(piece.shape, piece.x, piece.y)) {
                    gameOver();
                }
            }
            canHold = false;
        }

        // ---------- LOCKING & CLEARING ----------
        function lockPiece() {
            if (!currentPiece) return;
            const piece = currentPiece;
            let aboveVisible = true;

            for (let r = 0; r < piece.shape.length; r++) {
                for (let c = 0; c < piece.shape[r].length; c++) {
                    if (piece.shape[r][c]) {
                        const boardY = piece.y + r;
                        const boardX = piece.x + c;
                        if (boardY >= 0 && boardY < TOTAL_ROWS && boardX >= 0 && boardX < COLS) {
                            board[boardY][boardX] = piece.type;
                        }
                        if (boardY >= HIDDEN_ROWS) aboveVisible = false;
                    }
                }
            }

            // Check lock out
            if (aboveVisible) {
                gameOver();
                return;
            }

            // Check T-Spin before clearing
            const isTSpin = checkTSpin(piece);
            const isMini = isTSpin && checkTSpinMini(piece);

            // Clear lines
            const cleared = clearLines();

            // Scoring
            if (cleared > 0) {
                handleLineClearScore(cleared, isTSpin, isMini);
                combo++;
            } else {
                if (isTSpin) {
                    const points = isMini ? 100 : 400;
                    score += points * level;
                    setAction(isMini ? 'T-SPIN MINI' : 'T-SPIN');
                }
                combo = 0;
            }

            // Perfect clear check
            if (cleared > 0 && isBoardEmpty()) {
                score += 3500 * level;
                setAction('PERFECT CLEAR');
            }

            updateUI();
            spawnPiece();
        }

        function checkTSpin(piece) {
            if (piece.type !== 'T') return false;
            // Check 4 corners around T center
            const cx = piece.x + 1;
            const cy = piece.y + 1;
            const corners = [
                [cx - 1, cy - 1],
                [cx + 1, cy - 1],
                [cx - 1, cy + 1],
                [cx + 1, cy + 1]
            ];
            let filled = 0;
            for (const [x, y] of corners) {
                if (x < 0 || x >= COLS || y >= TOTAL_ROWS) {
                    filled++;
                } else if (y >= 0 && board[y][x]) {
                    filled++;
                }
            }
            return filled >= 3;
        }

        function checkTSpinMini(piece) {
            // Mini if the two "front" corners relative to rotation are not both filled
            // Simplified: check if the two corners adjacent to the T's pointing direction
            const rot = piece.rotation;
            const cx = piece.x + 1;
            const cy = piece.y + 1;
            // Front corners depend on rotation
            // Rotation 0: pointing up, front corners are top-left and top-right
            // Rotation 1: pointing right, front corners are top-right and bottom-right
            // Rotation 2: pointing down, front corners are bottom-left and bottom-right
            // Rotation 3: pointing left, front corners are top-left and bottom-left
            let frontCorners = [];
            if (rot === 0) frontCorners = [[cx-1, cy-1], [cx+1, cy-1]];
            else if (rot === 1) frontCorners = [[cx+1, cy-1], [cx+1, cy+1]];
            else if (rot === 2) frontCorners = [[cx-1, cy+1], [cx+1, cy+1]];
            else frontCorners = [[cx-1, cy-1], [cx-1, cy+1]];

            let filledFront = 0;
            for (const [x, y] of frontCorners) {
                if (x < 0 || x >= COLS || y >= TOTAL_ROWS) filledFront++;
                else if (y >= 0 && board[y][x]) filledFront++;
            }
            return filledFront < 2;
        }

        function clearLines() {
            let cleared = 0;
            for (let r = TOTAL_ROWS - 1; r >= 0; r--) {
                if (board[r].every(cell => cell !== null)) {
                    board.splice(r, 1);
                    board.unshift(new Array(COLS).fill(null));
                    cleared++;
                    r++;
                }
            }
            return cleared;
        }

        function isBoardEmpty() {
            for (let r = 0; r < TOTAL_ROWS; r++) {
                for (let c = 0; c < COLS; c++) {
                    if (board[r][c]) return false;
                }
            }
            return true;
        }

        function handleLineClearScore(cleared, isTSpin, isMini) {
            let basePoints = 0;
            let difficult = false;
            let label = '';

            if (isTSpin) {
                if (isMini) {
                    if (cleared === 1) { basePoints = 200; label = 'T-SPIN MINI SINGLE'; difficult = true; }
                    else { basePoints = 100; label = 'T-SPIN MINI'; }
                } else {
                    if (cleared === 1) { basePoints = 800; label = 'T-SPIN SINGLE'; difficult = true; }
                    else if (cleared === 2) { basePoints = 1200; label = 'T-SPIN DOUBLE'; difficult = true; }
                    else if (cleared === 3) { basePoints = 1600; label = 'T-SPIN TRIPLE'; difficult = true; }
                }
            } else {
                if (cleared === 1) { basePoints = 100; label = 'SINGLE'; }
                else if (cleared === 2) { basePoints = 300; label = 'DOUBLE'; }
                else if (cleared === 3) { basePoints = 500; label = 'TRIPLE'; }
                else if (cleared === 4) { basePoints = 800; label = 'TETRIS'; difficult = true; }
            }

            // Back-to-back
            if (difficult && lastClearWasDifficult) {
                basePoints = Math.floor(basePoints * 1.5);
                label = 'B2B ' + label;
            }
            lastClearWasDifficult = difficult;

            score += basePoints * level;

            // Combo
            if (combo > 0) {
                score += 50 * combo * level;
                if (combo >= 1) {
                    label += ' COMBO x' + (combo + 1);
                }
            }

            lines += cleared;
            const newLevel = Math.floor(lines / 10) + 1;
            if (newLevel > level) {
                level = newLevel;
            }

            setAction(label);
        }

        function setAction(text) {
            actionText = text;
            actionTimer = 1500;
        }

        // ---------- GAME OVER ----------
        function gameOver() {
            gameState = 'gameover';
            if (score > highScore) {
                highScore = score;
                localStorage.setItem('tetrisHighScore', highScore.toString());
            }
            updateUI();
            showOverlay('GAME OVER', 'Final Score: ' + score, 'Press R to restart');
        }

        // ---------- UI ----------
        function updateUI() {
            scoreDisplay.textContent = score;
            levelDisplay.textContent = level;
            linesDisplay.textContent = lines;
            highScoreDisplay.textContent = highScore;
        }

        function showOverlay(title, text, sub) {
            overlayTitle.textContent = title;
            overlayText.textContent = text;
            overlaySub.textContent = sub || '';
            overlay.classList.remove('hidden');
        }

        function hideOverlay() {
            overlay.classList.add('hidden');
        }

        // ---------- RENDERING ----------
        function drawBlock(ctx, x, y, size, color, alpha) {
            ctx.globalAlpha = alpha || 1;
            ctx.fillStyle = color;
            ctx.fillRect(x, y, size, size);
            // Bevel
            ctx.fillStyle = 'rgba(255,255,255,0.25)';
            ctx.fillRect(x, y, size, 2);
            ctx.fillRect(x, y, 2, size);
            ctx.fillStyle = 'rgba(0,0,0,0.25)';
            ctx.fillRect(x, y + size - 2, size, 2);
            ctx.fillRect(x + size - 2, y, 2, size);
            ctx.globalAlpha = 1;
        }

        function drawBoard() {
            boardCtx.clearRect(0, 0, boardCanvas.width, boardCanvas.height);
            // Background
            boardCtx.fillStyle = '#0a0d12';
            boardCtx.fillRect(0, 0, boardCanvas.width, boardCanvas.height);

            // Grid
            boardCtx.strokeStyle = '#1a2230';
            boardCtx.lineWidth = 1;
            for (let c = 0; c <= COLS; c++) {
                boardCtx.beginPath();
                boardCtx.moveTo(c * CELL_SIZE, 0);
                boardCtx.lineTo(c * CELL_SIZE, ROWS * CELL_SIZE);
                boardCtx.stroke();
            }
            for (let r = 0; r <= ROWS; r++) {
                boardCtx.beginPath();
                boardCtx.moveTo(0, r * CELL_SIZE);
                boardCtx.lineTo(COLS * CELL_SIZE, r * CELL_SIZE);
                boardCtx.stroke();
            }

            // Draw board cells (visible rows only)
            for (let r = HIDDEN_ROWS; r < TOTAL_ROWS; r++) {
                for (let c = 0; c < COLS; c++) {
                    if (board[r][c]) {
                        const drawY = (r - HIDDEN_ROWS) * CELL_SIZE;
                        drawBlock(boardCtx, c * CELL_SIZE, drawY, CELL_SIZE, COLORS[board[r][c]]);
                    }
                }
            }

            // Ghost piece
            if (currentPiece && gameState === 'playing') {
                const ghostY = getGhostY();
                const piece = currentPiece;
                for (let r = 0; r < piece.shape.length; r++) {
                    for (let c = 0; c < piece.shape[r].length; c++) {
                        if (piece.shape[r][c]) {
                            const boardY = ghostY + r;
                            if (boardY >= HIDDEN_ROWS) {
                                const drawY = (boardY - HIDDEN_ROWS) * CELL_SIZE;
                                const drawX = (piece.x + c) * CELL_SIZE;
                                boardCtx.globalAlpha = 0.25;
                                boardCtx.fillStyle = COLORS[piece.type];
                                boardCtx.fillRect(drawX, drawY, CELL_SIZE, CELL_SIZE);
                                boardCtx.globalAlpha = 1;
                                boardCtx.strokeStyle = COLORS[piece.type];
                                boardCtx.lineWidth = 1;
                                boardCtx.strokeRect(drawX + 0.5, drawY + 0.5, CELL_SIZE - 1, CELL_SIZE - 1);
                            }
                        }
                    }
                }
            }

            // Current piece
            if (currentPiece && gameState === 'playing') {
                const piece = currentPiece;
                for (let r = 0; r < piece.shape.length; r++) {
                    for (let c = 0; c < piece.shape[r].length; c++) {
                        if (piece.shape[r][c]) {
                            const boardY = piece.y + r;
                            if (boardY >= HIDDEN_ROWS) {
                                const drawY = (boardY - HIDDEN_ROWS) * CELL_SIZE;
                                const drawX = (piece.x + c) * CELL_SIZE;
                                drawBlock(boardCtx, drawX, drawY, CELL_SIZE, COLORS[piece.type]);
                            }
                        }
                    }
                }
            }
        }

        function getGhostY() {
            if (!currentPiece) return 0;
            let gy = currentPiece.y;
            while (!collides(currentPiece.shape, currentPiece.x, gy + 1)) {
                gy++;
            }
            return gy;
        }

        function drawMiniPiece(ctx, type, offsetX, offsetY, cellSize) {
            const shape = SHAPES[type];
            const color = COLORS[type];
            // Center the piece
            let minR = shape.length, maxR = -1, minC = shape[0].length, maxC = -1;
            for (let r = 0; r < shape.length; r++) {
                for (let c = 0; c < shape[r].length; c++) {
                    if (shape[r][c]) {
                        minR = Math.min(minR, r);
                        maxR = Math.max(maxR, r);
                        minC = Math.min(minC, c);
                        maxC = Math.max(maxC, c);
                    }
                }
            }
            const w = (maxC - minC + 1) * cellSize;
            const h = (maxR - minR + 1) * cellSize;
            const startX = offsetX + (120 - w) / 2;
            const startY = offsetY + (80 - h) / 2;

            for (let r = minR; r <= maxR; r++) {
                for (let c = minC; c <= maxC; c++) {
                    if (shape[r][c]) {
                        const x = startX + (c - minC) * cellSize;
                        const y = startY + (r - minR) * cellSize;
                        drawBlock(ctx, x, y, cellSize, color);
                    }
                }
            }
        }

        function drawHold() {
            holdCtx.clearRect(0, 0, holdCanvas.width, holdCanvas.height);
            holdCtx.fillStyle = '#0a0d12';
            holdCtx.fillRect(0, 0, holdCanvas.width, holdCanvas.height);
            if (holdPiece) {
                drawMiniPiece(holdCtx, holdPiece, 0, 0, 20);
            }
        }

        function drawNext() {
            nextCtx.clearRect(0, 0, nextCanvas.width, nextCanvas.height);
            nextCtx.fillStyle = '#0a0d12';
            nextCtx.fillRect(0, 0, nextCanvas.width, nextCanvas.height);
            for (let i = 0; i < Math.min(5, nextQueue.length); i++) {
                drawMiniPiece(nextCtx, nextQueue[i], 0, i * 52, 16);
            }
        }

        // ---------- GAME LOOP ----------
        function getGravityInterval() {
            const l = Math.max(1, level);
            return Math.pow(0.8 - (l - 1) * 0.007, l - 1);
        }

        function update(dt) {
            if (gameState !== 'playing') return;

            // Action label timer
            if (actionTimer > 0) {
                actionTimer -= dt;
                if (actionTimer <= 0) {
                    actionText = '';
                }
            }

            // DAS/ARR
            if (dasDirection !== 0) {
                dasTimer += dt;
                if (dasTimer >= DAS_DELAY) {
                    arrTimer += dt;
                    while (arrTimer >= ARR_DELAY) {
                        arrTimer -= ARR_DELAY;
                        if (movePiece(dasDirection, 0)) {
                            // moved
                        } else {
                            break;
                        }
                    }
                }
            }

            // Gravity
            const gravityInterval = getGravityInterval();
            const effectiveGravity = softDropActive ? gravityInterval / 20 : gravityInterval;
            gravityTimer += dt / 1000;

            if (gravityTimer >= effectiveGravity) {
                gravityTimer -= effectiveGravity;
                if (movePiece(0, 1)) {
                    if (softDropActive) score += 1;
                } else {
                    // Piece is resting
                    if (!isLocking) {
                        isLocking = true;
                        lockTimer = 0;
                    }
                }
            }

            // Lock delay
            if (isLocking) {
                lockTimer += dt;
                if (lockTimer >= 500) {
                    lockPiece();
                }
            }
        }

        function gameLoop(timestamp) {
            if (!lastTime) lastTime = timestamp;
            const dt = Math.min(timestamp - lastTime, 100);
            lastTime = timestamp;

            update(dt);
            drawBoard();
            drawHold();
            drawNext();

            // Action label
            if (actionText) {
                actionLabel.textContent = actionText;
            } else {
                actionLabel.textContent = '';
            }

            rafId = requestAnimationFrame(gameLoop);
        }

        // ---------- INPUT ----------
        const keys = {};

        document.addEventListener('keydown', (e) => {
            const key = e.key;

            if (gameState === 'start') {
                if (key === 'Enter') {
                    e.preventDefault();
                    resetGame();
                    gameState = 'playing';
                    hideOverlay();
                    lastTime = 0;
                }
                return;
            }

            if (gameState === 'gameover') {
                if (key === 'r' || key === 'R') {
                    e.preventDefault();
                    resetGame();
                    gameState = 'playing';
                    hideOverlay();
                    lastTime = 0;
                }
                return;
            }

            if (key === 'p' || key === 'P' || key === 'Escape') {
                e.preventDefault();
                if (gameState === 'playing') {
                    gameState = 'paused';
                    showOverlay('PAUSED', 'Press P or Esc to resume', '');
                } else if (gameState === 'paused') {
                    gameState = 'playing';
                    hideOverlay();
                    lastTime = 0;
                }
                return;
            }

            if (gameState !== 'playing') return;

            if (keys[key]) return; // prevent repeat for some keys
            keys[key] = true;

            switch (key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    movePiece(-1, 0);
                    dasDirection = -1;
                    dasTimer = 0;
                    arrTimer = 0;
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    movePiece(1, 0);
                    dasDirection = 1;
                    dasTimer = 0;
                    arrTimer = 0;
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    softDropActive = true;
                    break;
                case 'ArrowUp':
                case 'x':
                case 'X':
                    e.preventDefault();
                    rotatePiece('cw');
                    break;
                case 'z':
                case 'Z':
                case 'Control':
                    e.preventDefault();
                    rotatePiece('ccw');
                    break;
                case ' ':
                    e.preventDefault();
                    hardDrop();
                    break;
                case 'c':
                case 'C':
                case 'Shift':
                    e.preventDefault();
                    holdPieceAction();
                    break;
            }
        });

        document.addEventListener('keyup', (e) => {
            const key = e.key;
            keys[key] = false;

            if (key === 'ArrowLeft' && dasDirection === -1) {
                dasDirection = 0;
            }
            if (key === 'ArrowRight' && dasDirection === 1) {
                dasDirection = 0;
            }
            if (key === 'ArrowDown') {
                softDropActive = false;
            }
        });

        // Prevent default for space, arrows
        window.addEventListener('keydown', (e) => {
            if ([' ', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                if (gameState === 'playing') e.preventDefault();
            }
        }, { passive: false });

        // ---------- START ----------
        initBoard();
        updateUI();
        highScoreDisplay.textContent = highScore;
        showOverlay('TETRIS', 'Press Enter to start', '');
        rafId = requestAnimationFrame(gameLoop);

    })();
</script>
</body>
</html>
```