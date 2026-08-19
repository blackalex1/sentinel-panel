/**
 * Server Sentinel Guardian - Interactive Dashboard Mascot Renderer
 * High-performance 60 FPS HTML5 Canvas engine with reactive state machine,
 * server rackmount chassis, datacenter LED indicators, hypervisor reactor core,
 * and live server telemetry pulse.
 */

import { t } from "../../i18n.js";

export class SentinelServerMascot {
    constructor(canvasId, containerId) {
        this.canvas = document.getElementById(canvasId);
        this.container = document.getElementById(containerId);
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext("2d");
        this.isRunning = true;
        this.isShocking = false;
        this.shockTimer = 0;
        this.eyeOpenness = 1.0;
        this.eyeTargetOpenness = 1.0;
        
        // Metrics
        this.cpu = 0;
        this.ramPercent = 0;
        this.netSpeed = 0; // bytes/sec total
        
        // Animation Timers & Phases
        this.startTime = performance.now();
        this.lastFrameTime = performance.now();
        this.animationFrameId = null;
        
        // LED blinking states
        this.ledNetBlink = 0;
        this.ledActBlink = 0;
        
        // Interactive click callback
        this.onClickCallback = null;
        
        // Eye Color State
        this.currentEyeColor = { r: 16, g: 185, b: 129 }; // Emerald Green
        this.targetEyeColor = { r: 16, g: 185, b: 129 };

        this.init();
    }

    init() {
        this.resize();
        window.addEventListener("resize", () => this.resize());
        
        const clickTarget = this.container || this.canvas;
        if (clickTarget) {
            clickTarget.addEventListener("click", () => {
                this.triggerShock();
                if (this.onClickCallback) this.onClickCallback();
            });
        }

        // Start render loop
        this.startLoop();
    }

    setOnClick(cb) {
        this.onClickCallback = cb;
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const size = Math.max(Math.min(rect.width || 76, rect.height || 76), 64);
        
        this.canvas.width = size * dpr;
        this.canvas.height = size * dpr;
        this.width = size;
        this.height = size;
        this.dpr = dpr;
    }

    setRunningState(running) {
        if (this.isRunning !== running) {
            this.isRunning = running;
            if (running) {
                this.triggerShock();
            }
        }
        this.eyeTargetOpenness = running ? 1.0 : 0.0;
        this.targetEyeColor = running 
            ? { r: 16, g: 185, b: 129 }  // #10B981 Active Emerald
            : { r: 139, g: 92, b: 246 }; // #8B5CF6 Standby Violet
    }

    setMetrics(cpu, ramPercent, speedUp, speedDown) {
        this.cpu = cpu || 0;
        this.ramPercent = ramPercent || 0;
        this.netSpeed = (speedUp || 0) + (speedDown || 0);
    }

    triggerShock() {
        this.isShocking = true;
        this.shockTimer = performance.now();
    }

    startLoop() {
        const render = (now) => {
            const dt = Math.min((now - this.lastFrameTime) / 1000, 0.1);
            this.lastFrameTime = now;

            this.update(now, dt);
            this.draw(now);

            this.animationFrameId = requestAnimationFrame(render);
        };
        this.animationFrameId = requestAnimationFrame(render);
    }

    destroy() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
    }

    update(now, dt) {
        // Smooth eye openness interpolation
        const eyeSpeed = 4.0 * dt;
        this.eyeOpenness += (this.eyeTargetOpenness - this.eyeOpenness) * eyeSpeed;

        // Smooth eye color interpolation
        const colorSpeed = 6.0 * dt;
        this.currentEyeColor.r += (this.targetEyeColor.r - this.currentEyeColor.r) * colorSpeed;
        this.currentEyeColor.g += (this.targetEyeColor.g - this.currentEyeColor.g) * colorSpeed;
        this.currentEyeColor.b += (this.targetEyeColor.b - this.currentEyeColor.b) * colorSpeed;

        // Shock state timeout (600ms duration)
        if (this.isShocking && now - this.shockTimer > 600) {
            this.isShocking = false;
        }

        // LED blinking logic based on network speed & cpu
        this.ledNetBlink = Math.sin(now * (this.netSpeed > 1024 ? 0.035 : 0.008)) > 0 ? 1 : 0;
        this.ledActBlink = Math.sin(now * (0.01 + this.cpu * 0.0003)) > -0.2 ? 1 : 0;
    }

    draw(now) {
        const ctx = this.ctx;
        if (!ctx || !this.width) return;

        ctx.save();
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.scale(this.dpr, this.dpr);

        const w = this.width;
        const h = this.height;
        const s = Math.min(w, h) / 100;

        // Jitter Shake during shock
        let jitterX = 0;
        let jitterY = 0;
        if (this.isShocking) {
            const shockProgress = 1 - (now - this.shockTimer) / 600;
            jitterX = (Math.random() - 0.5) * 4 * shockProgress * s;
            jitterY = (Math.random() - 0.5) * 4 * shockProgress * s;
        }

        // Sleep Breathing Motion
        const sleepProgress = 1 - this.eyeOpenness;
        const sleepBreathingY = Math.sin(now * 0.0025) * 2.2 * sleepProgress * s;

        const ox = (w - 100 * s) / 2 + jitterX;
        const oy = (h - 100 * s) / 2 + jitterY + sleepBreathingY;

        const fx = (v) => ox + v * s;
        const fy = (v) => oy + v * s;

        const isRunning = this.isRunning;
        const eyeOpen = this.eyeOpenness;

        // Core Pulse dynamic speed (CPU accelerates heartbeat)
        const pulseRate = 0.0035 + (this.cpu / 100) * 0.0045;
        const heartbeat = 0.92 + Math.sin(now * pulseRate) * 0.12 * (0.3 + 0.7 * eyeOpen);

        // -------------------------------------------------------------
        // 1. TACTICAL RADAR BACKGROUND GLOW & RINGS
        // -------------------------------------------------------------
        const centerX = fx(50);
        const centerY = fy(50);
        const maxRadius = 46 * s;

        // Ambient radial background glow
        const bgGlow = ctx.createRadialGradient(centerX, centerY, 5 * s, centerX, centerY, maxRadius);
        if (isRunning) {
            bgGlow.addColorStop(0, "rgba(16, 185, 129, 0.18)");
            bgGlow.addColorStop(0.6, "rgba(6, 182, 212, 0.06)");
            bgGlow.addColorStop(1, "rgba(6, 8, 18, 0)");
        } else {
            bgGlow.addColorStop(0, "rgba(139, 92, 246, 0.14)");
            bgGlow.addColorStop(0.6, "rgba(124, 58, 237, 0.04)");
            bgGlow.addColorStop(1, "rgba(6, 8, 18, 0)");
        }
        ctx.fillStyle = bgGlow;
        ctx.beginPath();
        ctx.arc(centerX, centerY, maxRadius, 0, Math.PI * 2);
        ctx.fill();

        // Tactical Outer Dashed Bezel Ring
        ctx.save();
        ctx.strokeStyle = isRunning ? "rgba(16, 185, 129, 0.35)" : "rgba(139, 92, 246, 0.25)";
        ctx.lineWidth = 1.2 * s;
        ctx.setLineDash([4 * s, 6 * s]);
        ctx.beginPath();
        ctx.arc(centerX, centerY, 44 * s, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();

        // -------------------------------------------------------------
        // 2. SLEEPING PARTICLES: FLOATING "Z Z Z" (When in Standby)
        // -------------------------------------------------------------
        if (sleepProgress > 0.05) {
            const drawFloatingZ = (offsetMs, xBase, yBase) => {
                const zTime = ((now + offsetMs) % 2400) / 2400;
                const zX = fx(xBase + zTime * 14);
                const zY = fy(yBase - zTime * 18);
                const zAlpha = Math.sin(zTime * Math.PI) * 0.75 * sleepProgress;
                const zScale = (0.4 + zTime * 0.4) * s;

                ctx.save();
                ctx.strokeStyle = `rgba(167, 139, 250, ${zAlpha})`;
                ctx.lineWidth = 1.8 * zScale;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";

                ctx.beginPath();
                ctx.moveTo(zX - 4 * zScale, zY - 5 * zScale);
                ctx.lineTo(zX + 4 * zScale, zY - 5 * zScale);
                ctx.lineTo(zX - 4 * zScale, zY + 5 * zScale);
                ctx.lineTo(zX + 4 * zScale, zY + 5 * zScale);
                ctx.stroke();
                ctx.restore();
            };

            drawFloatingZ(0, 62, 26);
            drawFloatingZ(800, 60, 28);
            drawFloatingZ(1600, 58, 30);
        }

        // -------------------------------------------------------------
        // 3. ELECTRIC SPARK BOLTS (Shock / Boot / Click)
        // -------------------------------------------------------------
        if (this.isShocking) {
            const sparkAlpha = Math.random() * 0.9 + 0.1;
            ctx.save();
            ctx.strokeStyle = Math.random() > 0.5 ? `rgba(6, 182, 212, ${sparkAlpha})` : `rgba(250, 204, 21, ${sparkAlpha})`;
            ctx.lineWidth = 2.2 * s;
            ctx.lineCap = "round";

            // Left Bolt
            ctx.beginPath();
            ctx.moveTo(fx(24), fy(8));
            ctx.lineTo(fx(20), fy(18));
            ctx.lineTo(fx(26), fy(20));
            ctx.lineTo(fx(22), fy(30));
            ctx.stroke();

            // Right Bolt
            ctx.beginPath();
            ctx.moveTo(fx(76), fy(8));
            ctx.lineTo(fx(80), fy(18));
            ctx.lineTo(fx(74), fy(20));
            ctx.lineTo(fx(78), fy(30));
            ctx.stroke();
            ctx.restore();
        }

        // -------------------------------------------------------------
        // 4. SERVER RACK MOUNT EARS / OPTICAL ANTENNAS (Left & Right)
        // -------------------------------------------------------------
        const primaryColor = isRunning ? "#10B981" : "#8B5CF6";

        // Left Server Rack Ear & Optical Guide
        ctx.save();
        ctx.fillStyle = isRunning ? "rgba(16, 185, 129, 0.15)" : "rgba(139, 92, 246, 0.12)";
        ctx.strokeStyle = isRunning ? "#22D3EE" : "#8B5CF6";
        ctx.lineWidth = 2.4 * s;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        // Left Fin Beam
        ctx.beginPath();
        ctx.moveTo(fx(36), fy(22));
        ctx.lineTo(fx(24), fy(8));
        ctx.lineTo(fx(18), fy(12));
        ctx.lineTo(fx(26), fy(28));
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Left Server Rack Mount Hole
        ctx.fillStyle = "#060812";
        ctx.beginPath();
        ctx.arc(fx(23), fy(16), 1.8 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = isRunning ? "#34D399" : "#A78BFA";
        ctx.lineWidth = 1 * s;
        ctx.stroke();

        // Left Optical Node Tip (Glowing Fiber Transceiver)
        const tipGlow = isRunning ? (0.6 + 0.4 * heartbeat) : 0.4;
        ctx.fillStyle = isRunning ? `rgba(34, 211, 238, ${tipGlow})` : `rgba(139, 92, 246, 0.5)`;
        ctx.beginPath();
        ctx.arc(fx(24), fy(8), 4.2 * s * (isRunning ? heartbeat : 1), 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(fx(24), fy(8), 1.6 * s, 0, Math.PI * 2);
        ctx.fill();

        // Right Server Rack Ear & Optical Guide
        ctx.fillStyle = isRunning ? "rgba(16, 185, 129, 0.15)" : "rgba(139, 92, 246, 0.12)";
        ctx.strokeStyle = isRunning ? "#22D3EE" : "#8B5CF6";
        ctx.lineWidth = 2.4 * s;

        ctx.beginPath();
        ctx.moveTo(fx(64), fy(22));
        ctx.lineTo(fx(76), fy(8));
        ctx.lineTo(fx(82), fy(12));
        ctx.lineTo(fx(74), fy(28));
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Right Server Rack Mount Hole
        ctx.fillStyle = "#060812";
        ctx.beginPath();
        ctx.arc(fx(77), fy(16), 1.8 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = isRunning ? "#34D399" : "#A78BFA";
        ctx.lineWidth = 1 * s;
        ctx.stroke();

        // Right Optical Node Tip
        ctx.fillStyle = isRunning ? `rgba(34, 211, 238, ${tipGlow})` : `rgba(139, 92, 246, 0.5)`;
        ctx.beginPath();
        ctx.arc(fx(76), fy(8), 4.2 * s * (isRunning ? heartbeat : 1), 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(fx(76), fy(8), 1.6 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // -------------------------------------------------------------
        // 5. SERVER BLADE CHASSIS & REINFORCED SHIELD
        // -------------------------------------------------------------
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(14));
        ctx.lineTo(fx(76), fy(14));
        ctx.lineTo(fx(83), fy(24));
        ctx.lineTo(fx(83), fy(64));
        ctx.lineTo(fx(50), fy(95));
        ctx.lineTo(fx(17), fy(64));
        ctx.lineTo(fx(17), fy(24));
        ctx.lineTo(fx(24), fy(14));
        ctx.closePath();

        // Deep Server Carbon Body Fill
        const bodyGrad = ctx.createLinearGradient(fx(50), fy(14), fx(50), fy(95));
        if (isRunning) {
            bodyGrad.addColorStop(0, "#0e1a16");
            bodyGrad.addColorStop(0.5, "#091210");
            bodyGrad.addColorStop(1, "#050a08");
        } else {
            bodyGrad.addColorStop(0, "#161026");
            bodyGrad.addColorStop(0.5, "#0e0a19");
            bodyGrad.addColorStop(1, "#06040c");
        }
        ctx.fillStyle = bodyGrad;
        ctx.fill();

        // Outer Reinforced Bezel Border
        ctx.strokeStyle = isRunning ? "#10B981" : "rgba(139, 92, 246, 0.7)";
        ctx.lineWidth = 3.5 * s;
        ctx.stroke();
        ctx.restore();

        // -------------------------------------------------------------
        // 6. DATACENTER COOLING VENTS / HEATSINK SLATS (Cheeks)
        // -------------------------------------------------------------
        const drawCoolingVent = (x1, y1, x2, y2, color) => {
            ctx.save();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.8 * s;
            ctx.lineCap = "round";
            for (let i = 0; i < 3; i++) {
                const dy = i * 4.5 * s;
                ctx.beginPath();
                ctx.moveTo(fx(x1), fy(y1) + dy);
                ctx.lineTo(fx(x2), fy(y2) + dy);
                ctx.stroke();
            }
            ctx.restore();
        };

        const ventColor = isRunning ? "rgba(6, 182, 212, 0.45)" : "rgba(139, 92, 246, 0.3)";
        drawCoolingVent(20, 48, 30, 54, ventColor);
        drawCoolingVent(80, 48, 70, 54, ventColor);

        // -------------------------------------------------------------
        // 7. STATUS INDICATOR LED ARRAY (PWR, LAN, ACT, SEC)
        // -------------------------------------------------------------
        const drawLed = (x, y, label, isActive, activeColor) => {
            ctx.save();
            const color = isActive ? activeColor : "rgba(255, 255, 255, 0.15)";
            // Outer subtle LED halo
            if (isActive) {
                ctx.fillStyle = activeColor.replace("1)", "0.35)");
                ctx.beginPath();
                ctx.arc(fx(x), fy(y), 2.8 * s, 0, Math.PI * 2);
                ctx.fill();
            }
            // Inner Core Dot
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(fx(x), fy(y), 1.4 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        };

        // 4 Forehead Status LEDs:
        // LED 1: PWR (Power State)
        drawLed(38, 22, "PWR", true, isRunning ? "rgba(16, 185, 129, 1)" : "rgba(245, 158, 11, 1)");
        // LED 2: LAN (Network RX/TX Blink)
        drawLed(46, 22, "LAN", isRunning && this.ledNetBlink === 1, "rgba(6, 182, 212, 1)");
        // LED 3: ACT (Activity Heartbeat)
        drawLed(54, 22, "ACT", isRunning && this.ledActBlink === 1, "rgba(52, 211, 153, 1)");
        // LED 4: SEC (Security Shield Guard)
        drawLed(62, 22, "SEC", isRunning, "rgba(139, 92, 246, 1)");

        // -------------------------------------------------------------
        // 8. SERVER TERMINAL VISOR & EYES
        // -------------------------------------------------------------
        const er = Math.round(this.currentEyeColor.r);
        const eg = Math.round(this.currentEyeColor.g);
        const eb = Math.round(this.currentEyeColor.b);

        if (eyeOpen > 0.05) {
            // Open Awake Matrix Terminal Eyes
            const eyeBloom = 10 * s * (0.85 + 0.25 * heartbeat) * eyeOpen;
            
            // Left Eye Radial Bloom
            const leftGlow = ctx.createRadialGradient(fx(36), fy(36), 1 * s, fx(36), fy(36), eyeBloom);
            leftGlow.addColorStop(0, `rgba(${er}, ${eg}, ${eb}, ${0.5 * eyeOpen})`);
            leftGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
            ctx.fillStyle = leftGlow;
            ctx.beginPath();
            ctx.arc(fx(36), fy(36), eyeBloom, 0, Math.PI * 2);
            ctx.fill();

            // Right Eye Radial Bloom
            const rightGlow = ctx.createRadialGradient(fx(64), fy(36), 1 * s, fx(64), fy(36), eyeBloom);
            rightGlow.addColorStop(0, `rgba(${er}, ${eg}, ${eb}, ${0.5 * eyeOpen})`);
            rightGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
            ctx.fillStyle = rightGlow;
            ctx.beginPath();
            ctx.arc(fx(64), fy(36), eyeBloom, 0, Math.PI * 2);
            ctx.fill();

            // Left Eye Polygon
            const eyeHeight = 4.5 * eyeOpen;
            ctx.save();
            ctx.fillStyle = `rgba(${er}, ${eg}, ${eb}, ${eyeOpen})`;
            ctx.beginPath();
            ctx.moveTo(fx(27), fy(36 - eyeHeight));
            ctx.lineTo(fx(44), fy(36 - eyeHeight));
            ctx.lineTo(fx(42), fy(36 + eyeHeight));
            ctx.lineTo(fx(29), fy(36 + eyeHeight));
            ctx.closePath();
            ctx.fill();

            // Right Eye Polygon
            ctx.beginPath();
            ctx.moveTo(fx(56), fy(36 - eyeHeight));
            ctx.lineTo(fx(73), fy(36 - eyeHeight));
            ctx.lineTo(fx(71), fy(36 + eyeHeight));
            ctx.lineTo(fx(58), fy(36 + eyeHeight));
            ctx.closePath();
            ctx.fill();

            // Inner Laser Terminal Highlights
            ctx.fillStyle = "#ffffff";
            ctx.beginPath();
            ctx.arc(fx(35.5), fy(36), 1.5 * s * eyeOpen, 0, Math.PI * 2);
            ctx.arc(fx(64.5), fy(36), 1.5 * s * eyeOpen, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }

        if (sleepProgress > 0.05) {
            // Standby Sleep Curved Terminal Bars
            ctx.save();
            ctx.strokeStyle = `rgba(${er}, ${eg}, ${eb}, ${0.85 * sleepProgress})`;
            ctx.lineWidth = 2.8 * s;
            ctx.lineCap = "round";

            // Left Closed Bar
            ctx.beginPath();
            ctx.moveTo(fx(28), fy(37));
            ctx.quadraticCurveTo(fx(35.5), fy(41), fx(43), fy(37));
            ctx.stroke();

            // Right Closed Bar
            ctx.beginPath();
            ctx.moveTo(fx(57), fy(37));
            ctx.quadraticCurveTo(fx(64.5), fy(41), fx(72), fy(37));
            ctx.stroke();
            ctx.restore();
        }

        // -------------------------------------------------------------
        // 9. HYPERVISOR REACTOR CORE (Central Power Unit)
        // -------------------------------------------------------------
        const coreScale = 0.85 + (heartbeat - 0.85) * eyeOpen;

        // Expanding Plasma Waves when online
        if (eyeOpen > 0.1) {
            const wave1Phase = ((now % 1800) / 1800);
            const wave2Phase = (((now + 900) % 1800) / 1800);

            const drawWave = (phase, col) => {
                const r = (8 + 16 * phase) * s;
                const a = (1 - phase) * 0.4 * eyeOpen;
                ctx.save();
                ctx.strokeStyle = col.replace("ALPHA", a.toFixed(2));
                ctx.lineWidth = 1.4 * s;
                ctx.beginPath();
                ctx.arc(fx(50), fy(62), r, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            };

            drawWave(wave1Phase, "rgba(6, 182, 212, ALPHA)");
            drawWave(wave2Phase, "rgba(16, 185, 129, ALPHA)");
        }

        // Outer Hex/Diamond Reactor
        ctx.save();
        ctx.fillStyle = isRunning ? "#10B981" : "#6D28D9";
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(62 - 14 * coreScale));
        ctx.lineTo(fx(50 + 12 * coreScale), fy(62 - 2 * coreScale));
        ctx.lineTo(fx(50), fy(62 + 17 * coreScale));
        ctx.lineTo(fx(50 - 12 * coreScale), fy(62 - 2 * coreScale));
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = isRunning ? "#34D399" : "#A78BFA";
        ctx.lineWidth = 1.2 * s;
        ctx.stroke();

        // Inner Power Spark
        const innerScale = coreScale * 0.7;
        ctx.fillStyle = isRunning ? "#22D3EE" : "#8B5CF6";
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(62 - 9 * innerScale));
        ctx.lineTo(fx(50 + 7 * innerScale), fy(62 - 2 * innerScale));
        ctx.lineTo(fx(50), fy(62 + 11 * innerScale));
        ctx.lineTo(fx(50 - 7 * innerScale), fy(62 - 2 * innerScale));
        ctx.closePath();
        ctx.fill();

        // Center White Radiant Heart
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(62 - 4 * innerScale));
        ctx.lineTo(fx(50 + 3 * innerScale), fy(62 - 1 * innerScale));
        ctx.lineTo(fx(50), fy(62 + 4 * innerScale));
        ctx.lineTo(fx(50 - 3 * innerScale), fy(62 - 1 * innerScale));
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        ctx.restore();
    }
}
