/**
 * Server Sentinel Guardian - Interactive 60 FPS HTML5 Canvas Mascot Engine (Production)
 * Authentic High-Tech Datacenter Cyber Mecha Identity
 * Features:
 * - Active cooling turbines on lower cheeks with realistic RPM physics & inertia deceleration
 * - Clean dark tinted visor with polygonal neon HUD eyes, mouse gaze tracking, and smooth blinking
 * - Smooth, cinematic sleep (CRT standby slit, slow breath) and wakeup (quantum ignition flash)
 * - Titanium-clamped Diamond Quantum Arc Reactor with calm luminous breathing (no geometric warping)
 * - 3-tier angled telemetry chevron notches on upper cheek cowlings
 * - Multi-form-factor support ('blade', 'monolith', 'orbital', 'mecha')
 * - Electric EMP shockwave burst on click
 * - 100% static card position (no wobble / no tilt)
 */

import { t } from "../../i18n.js";

export class SentinelServerMascot {
    constructor(canvasId, containerId, formFactor = 'blade') {
        this.canvas = typeof canvasId === "string" ? document.getElementById(canvasId) : canvasId;
        this.container = typeof containerId === "string" ? document.getElementById(containerId) : containerId;
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext("2d");
        this.isRunning = true;
        this.formFactor = formFactor;
        
        // Sleep & Wakeup Smooth Interpolation
        this.sleepProgress = 0.0;
        this.targetSleepProgress = 0.0;
        this.wakeFlash = 0.0;

        // Shock / EMP on Click
        this.isShocking = false;
        this.shockTimer = 0;
        this.shockDuration = 650;
        
        // Eye Dynamics
        this.eyeOpenness = 1.0;
        this.eyeTargetOpenness = 1.0;
        this.blinkTimer = 0;
        this.nextBlinkTime = performance.now() + 3000 + Math.random() * 4000;
        
        // Interactive Mouse Tracking Gaze
        this.gazeX = 0;
        this.gazeY = 0;
        this.targetGazeX = 0;
        this.targetGazeY = 0;
        this.lastMouseMoveTime = performance.now();
        this.isHovered = false;

        // Metrics Telemetry
        this.cpu = 0;
        this.ramPercent = 0;
        this.netSpeed = 0; // bytes/sec
        
        // Turbine Dynamics
        this.turbineAngle = 0;
        this.turbineRPM = 300;
        this.targetTurbineRPM = 300;

        // Timers & Physics
        this.startTime = performance.now();
        this.lastFrameTime = performance.now();
        this.animationFrameId = null;
        
        // Burst Particles
        this.shockParticles = [];
        this.electricArcs = [];
        this.onClickCallback = null;
        
        // Signature Matrix Emerald Color (#10B981)
        this.currentColor = { r: 16, g: 185, b: 129 };
        this.targetColor = { r: 16, g: 185, b: 129 };

        // --- Optimization: gradient cache (recreated only on canvas resize) ---
        this._cachedChassisGrad = null;
        this._cachedChassisGradW = -1;

        // --- Optimization: adaptive frame rate ---
        this._lastRenderTime = 0;

        // --- Optimization: pause rendering when off-screen / tab hidden ---
        this._isVisible = true;
        this._observer = null;

        this.init();
    }

    init() {
        this.resize();

        // Named handlers — stored as instance properties so destroy() can removeEventListener
        this._onResize = () => this.resize();
        this._onMouseMove = (e) => {
            if (!this.canvas || !this.isRunning) return;
            this.lastMouseMoveTime = performance.now();
            // Use cached rect — no forced layout recalculation on every pointer event
            const rect = this._canvasRect;
            if (!rect) return;
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            const dx = (e.clientX - centerX) / (window.innerWidth / 2);
            const dy = (e.clientY - centerY) / (window.innerHeight / 2);

            this.targetGazeX = Math.max(-1, Math.min(1, dx * 1.4));
            this.targetGazeY = Math.max(-1, Math.min(1, dy * 1.4));
        };
        this._onMouseLeave = () => {
            this.targetGazeX = 0;
            this.targetGazeY = 0;
        };
        this._onVisibilityChange = () => {
            this._isVisible = !document.hidden;
        };

        window.addEventListener("resize", this._onResize);
        window.addEventListener("mousemove", this._onMouseMove);
        window.addEventListener("mouseleave", this._onMouseLeave);

        const trackTarget = this.container || this.canvas;
        if (trackTarget) {
            this._onContainerEnter = () => {
                this.isHovered = true;
                if (this.isRunning) this.triggerMicroSparks(4);
            };
            this._onContainerLeave = () => { this.isHovered = false; };
            this._onContainerClick = () => {
                this.triggerShock();
                if (this.onClickCallback) this.onClickCallback();
            };
            trackTarget.addEventListener("mouseenter", this._onContainerEnter);
            trackTarget.addEventListener("mouseleave", this._onContainerLeave);
            trackTarget.addEventListener("click", this._onContainerClick);
            this._trackTarget = trackTarget;
        }

        this.startLoop();

        // Pause rendering entirely when mascot is off-screen (sidebar scrolled away etc.)
        if (typeof IntersectionObserver !== 'undefined') {
            this._observer = new IntersectionObserver(
                (entries) => { this._isVisible = entries[0].isIntersecting; },
                { threshold: 0.01 }
            );
            this._observer.observe(this.canvas);
        }

        // Pause rendering when browser tab is hidden (browser already pauses rAF, but
        // this also stops the update() physics tick that runs before draw check)
        document.addEventListener('visibilitychange', this._onVisibilityChange);
    }

    setOnClick(cb) {
        this.onClickCallback = cb;
    }

    setFormFactor(ff) {
        if (['blade', 'monolith', 'orbital', 'mecha'].includes(ff)) {
            this.formFactor = ff;
            this.triggerMicroSparks(6);
        }
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const size = Math.max(Math.min(rect.width || 140, rect.height || 140), 64);
        
        this.canvas.width = size * dpr;
        this.canvas.height = size * dpr;
        this.width = size;
        this.height = size;
        this.dpr = dpr;

        // Cache rect for mousemove — avoids forced layout recalculation on every pointer event
        this._canvasRect = this.canvas.getBoundingClientRect();
    }

    setRunningState(running) {
        if (this.isRunning !== running) {
            this.isRunning = running;
            if (running) {
                this.wakeFlash = 1.0;
                this.triggerMicroSparks(6);
            } else {
                this.targetGazeX = 0;
                this.targetGazeY = 0.25;
            }
        }
        this.targetSleepProgress = running ? 0.0 : 1.0;
        this.eyeTargetOpenness = running ? 1.0 : 0.0;
        this.targetColor = running 
            ? (this.cpu > 80 ? { r: 239, g: 68, b: 68 } : { r: 16, g: 185, b: 129 })
            : { r: 139, g: 92, b: 246 };
    }

    setMetrics(cpu, ramPercent, speedUp, speedDown) {
        this.cpu = cpu || 0;
        this.ramPercent = ramPercent || 0;
        this.netSpeed = (speedUp || 0) + (speedDown || 0);

        if (this.isRunning) {
            this.targetTurbineRPM = 200 + (this.cpu / 100) * 2200;
            if (this.cpu > 80) {
                this.targetColor = { r: 239, g: 68, b: 68 };
            } else {
                this.targetColor = { r: 16, g: 185, b: 129 };
            }
        } else {
            this.targetTurbineRPM = 0;
        }
    }

    triggerMicroSparks(count = 4) {
        for (let i = 0; i < count; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 15 + Math.random() * 25;
            this.shockParticles.push({
                x: 50 + (Math.random() - 0.5) * 24,
                y: 56 + (Math.random() - 0.5) * 24,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                life: 0.5 + Math.random() * 0.3,
                size: 1.2 + Math.random() * 1.5,
                color: Math.random() > 0.5 ? "#22D3EE" : "#10B981"
            });
        }
    }

    triggerShock() {
        this.isShocking = true;
        this.shockTimer = performance.now();

        this.shockParticles = [];
        for (let i = 0; i < 22; i++) {
            const angle = (i / 22) * Math.PI * 2 + (Math.random() - 0.5) * 0.3;
            const speed = 35 + Math.random() * 55;
            this.shockParticles.push({
                x: 50,
                y: 56,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                life: 1.0,
                size: 1.8 + Math.random() * 2.6,
                color: i % 2 === 0 ? "#22D3EE" : "#10B981"
            });
        }

        this.electricArcs = [];
        for (let k = 0; k < 3; k++) {
            this.electricArcs.push({ fromX: 20, fromY: 6, toX: 50, toY: 58, life: 0.45, color: "#22D3EE" });
            this.electricArcs.push({ fromX: 80, fromY: 6, toX: 50, toY: 58, life: 0.45, color: "#10B981" });
        }
    }

    startLoop() {
        const render = (now) => {
            // Skip entirely when off-screen or tab hidden
            if (!this._isVisible) {
                this.animationFrameId = requestAnimationFrame(render);
                return;
            }

            // Adaptive frame rate:
            //   - Active effects (EMP/shock/particles) → 60fps for smooth burst
            //   - Running normally                     → 30fps (imperceptible vs 60fps)
            //   - Fully asleep (sleepProgress > 0.97)  → 4fps via setTimeout (not rAF)
            const hasEffects = this.shockParticles.length > 0 ||
                               this.electricArcs.length > 0 ||
                               this.isShocking;
            const fullyAsleep = !this.isRunning && this.sleepProgress > 0.97;
            const targetFPS   = hasEffects ? 60 : 30;
            const minInterval = 1000 / targetFPS;

            if (!fullyAsleep && now - this._lastRenderTime < minInterval) {
                this.animationFrameId = requestAnimationFrame(render);
                return;
            }
            this._lastRenderTime = now;

            const dt = Math.min((now - this.lastFrameTime) / 1000, 0.1);
            this.lastFrameTime = now;

            this.update(now, dt);
            this.draw(now);

            if (fullyAsleep) {
                // Switch from rAF (60-144Hz) to setTimeout (~4fps) to save idle GPU/CPU cycles.
                // rAF resumes automatically when isRunning becomes true on the next tick.
                this._sleepTimeoutId = setTimeout(() => {
                    this.animationFrameId = requestAnimationFrame(render);
                }, 250);
            } else {
                this.animationFrameId = requestAnimationFrame(render);
            }
        };
        this.animationFrameId = requestAnimationFrame(render);
    }

    destroy() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
        if (this._sleepTimeoutId) {
            clearTimeout(this._sleepTimeoutId);
            this._sleepTimeoutId = null;
        }
        if (this._observer) {
            this._observer.disconnect();
        }
        // Remove all global listeners — prevents memory leaks on SPA navigation
        window.removeEventListener("resize", this._onResize);
        window.removeEventListener("mousemove", this._onMouseMove);
        window.removeEventListener("mouseleave", this._onMouseLeave);
        document.removeEventListener('visibilitychange', this._onVisibilityChange);
        if (this._trackTarget) {
            this._trackTarget.removeEventListener("mouseenter", this._onContainerEnter);
            this._trackTarget.removeEventListener("mouseleave", this._onContainerLeave);
            this._trackTarget.removeEventListener("click", this._onContainerClick);
        }
    }

    update(now, dt) {
        // Sleep progress lerp
        const sleepTransitionSpeed = 3.5 * dt;
        this.sleepProgress += (this.targetSleepProgress - this.sleepProgress) * sleepTransitionSpeed;

        if (this.wakeFlash > 0) {
            this.wakeFlash = Math.max(0, this.wakeFlash - 2.2 * dt);
        }

        // Eye openness & blink
        if (this.isRunning && now > this.nextBlinkTime) {
            this.eyeTargetOpenness = 0.05;
            if (now > this.nextBlinkTime + 120) {
                this.eyeTargetOpenness = 1.0;
                this.nextBlinkTime = now + 2600 + Math.random() * 4200;
            }
        }

        const eyeSpeed = 4.5 * dt;
        this.eyeOpenness += (this.eyeTargetOpenness - this.eyeOpenness) * eyeSpeed;

        // Color interpolation
        const colorSpeed = 4.0 * dt;
        this.currentColor.r += (this.targetColor.r - this.currentColor.r) * colorSpeed;
        this.currentColor.g += (this.targetColor.g - this.currentColor.g) * colorSpeed;
        this.currentColor.b += (this.targetColor.b - this.currentColor.b) * colorSpeed;

        // Autonomous Idle Gaze Scan
        if (now - this.lastMouseMoveTime > 3000 && this.isRunning) {
            const idleCycle = Math.sin(now * 0.0012);
            this.targetGazeX = idleCycle * 0.45;
            this.targetGazeY = Math.cos(now * 0.0008) * 0.25;
        }

        // Smooth Gaze follow
        const gazeFollowSpeed = 6.0 * dt;
        this.gazeX += (this.targetGazeX - this.gazeX) * gazeFollowSpeed;
        this.gazeY += (this.targetGazeY - this.gazeY) * gazeFollowSpeed;

        // Turbine physical rotation & inertia
        const inertiaSpeed = (this.targetTurbineRPM < this.turbineRPM ? 1.8 : 3.5);
        this.turbineRPM += (this.targetTurbineRPM - this.turbineRPM) * (inertiaSpeed * dt);
        this.turbineAngle += (this.turbineRPM * 0.06) * dt;

        // Shock state timeout
        if (this.isShocking && now - this.shockTimer > this.shockDuration) {
            this.isShocking = false;
        }

        // Update shock particles
        for (let i = this.shockParticles.length - 1; i >= 0; i--) {
            const p = this.shockParticles[i];
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            p.life -= 1.8 * dt;
            if (p.life <= 0) this.shockParticles.splice(i, 1);
        }

        for (let i = this.electricArcs.length - 1; i >= 0; i--) {
            this.electricArcs[i].life -= 3.0 * dt;
            if (this.electricArcs[i].life <= 0) this.electricArcs.splice(i, 1);
        }
    }

    draw(now) {
        const ctx = this.ctx;
        if (!ctx || !this.width) return;

        ctx.save();
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.scale(this.dpr, this.dpr);

        const w = this.width;
        const h = this.height;
        const s = Math.min(w, h) / 116;
        const fx = (x) => (x - 50) * s + w / 2;
        const fy = (y) => (y - 48) * s + h / 2;

        const isAwake = 1 - this.sleepProgress;
        const breatheFreq = 0.0022 * (1 - this.sleepProgress * 0.55);
        const breatheAmp = 1.5 * (1 - this.sleepProgress * 0.4);
        const breathe = Math.sin(now * breatheFreq) * breatheAmp;

        let shockOffsetY = 0;
        if (this.isShocking) {
            const progress = (now - this.shockTimer) / this.shockDuration;
            shockOffsetY = Math.sin(progress * Math.PI * 4) * (1 - progress) * 3.5;
        }

        const mainR = Math.round(this.currentColor.r);
        const mainG = Math.round(this.currentColor.g);
        const mainB = Math.round(this.currentColor.b);
        const mainColor = `rgb(${mainR}, ${mainG}, ${mainB})`;
        const signatureEmerald = "#10B981";
        const accentCyan = "#22D3EE";
        const armorBorderColor = this.isRunning ? (this.cpu > 80 ? "#EF4444" : signatureEmerald) : "#8B5CF6";

        // 1. Radial Ambient Halo
        ctx.save();
        const haloAlpha = (0.22 * isAwake + 0.06 * this.sleepProgress);
        const halo = ctx.createRadialGradient(fx(50), fy(52 + shockOffsetY), 8 * s, fx(50), fy(52 + shockOffsetY), 48 * s);
        halo.addColorStop(0, `rgba(${mainR}, ${mainG}, ${mainB}, ${haloAlpha})`);
        halo.addColorStop(0.6, `rgba(34, 211, 238, ${0.08 * isAwake + 0.02 * this.sleepProgress})`);
        halo.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(fx(50), fy(52 + shockOffsetY), 48 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // 2. Beacons & Radio Wave Pulses (Generous headroom, zero clipping)
        ctx.save();
        ctx.fillStyle = "#1e293b";
        ctx.strokeStyle = `rgba(34, 211, 238, ${0.5 * isAwake + 0.2 * this.sleepProgress})`;
        ctx.lineWidth = 1.2 * s;
        ctx.beginPath();
        ctx.moveTo(fx(24), fy(24 + shockOffsetY));
        ctx.lineTo(fx(20), fy(6 + shockOffsetY));
        ctx.lineTo(fx(32), fy(14 + shockOffsetY));
        ctx.closePath();
        ctx.moveTo(fx(76), fy(24 + shockOffsetY));
        ctx.lineTo(fx(80), fy(6 + shockOffsetY));
        ctx.lineTo(fx(68), fy(14 + shockOffsetY));
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        const beaconGlow = isAwake * (8 + Math.min((this.netSpeed || 0) / (1024 * 300), 8)) + this.sleepProgress * 4;
        ctx.fillStyle = this.isRunning ? (this.cpu > 80 ? "#EF4444" : accentCyan) : "#8B5CF6";
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = Math.min(beaconGlow, 6) * s;
        ctx.beginPath();
        ctx.arc(fx(20), fy(6 + shockOffsetY), 2.4 * s, 0, Math.PI * 2);
        ctx.arc(fx(80), fy(6 + shockOffsetY), 2.4 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        if (isAwake > 0.05) {
            const waveSpeed = 0.002 + Math.min((this.netSpeed || 0) / (1024 * 400), 0.006);
            const wavePhase = (now * waveSpeed) % 1;
            const waveAlpha = (0.25 + Math.min((this.netSpeed || 0) / (1024 * 1000), 0.5)) * isAwake * (1 - wavePhase);
            ctx.save();
            ctx.strokeStyle = `rgba(34, 211, 238, ${waveAlpha})`;
            ctx.lineWidth = 1.3 * s;
            ctx.beginPath();
            ctx.arc(fx(20), fy(6 + shockOffsetY), 3.0 * s + wavePhase * 7.5 * s, 0, Math.PI * 2);
            ctx.arc(fx(80), fy(6 + shockOffsetY), 3.0 * s + wavePhase * 7.5 * s, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
        }

        // 3. Chassis Armor Silhouette
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(12 + shockOffsetY));
        ctx.lineTo(fx(74), fy(16 + shockOffsetY));
        ctx.lineTo(fx(88), fy(34 + shockOffsetY));
        ctx.lineTo(fx(80), fy(68 + shockOffsetY));
        ctx.lineTo(fx(50), fy(94 + shockOffsetY));
        ctx.lineTo(fx(20), fy(68 + shockOffsetY));
        ctx.lineTo(fx(12), fy(34 + shockOffsetY));
        ctx.lineTo(fx(26), fy(16 + shockOffsetY));
        ctx.closePath();

        // Cache chassis gradient — recreate only when canvas size changes (not every frame)
        if (this._cachedChassisGradW !== this.width) {
            const g = ctx.createLinearGradient(fx(50), fy(12), fx(50), fy(94));
            g.addColorStop(0, "#111827");
            g.addColorStop(0.5, "#091811");
            g.addColorStop(1, "#030a06");
            this._cachedChassisGrad = g;
            this._cachedChassisGradW = this.width;
        }
        ctx.fillStyle = this._cachedChassisGrad;
        ctx.fill();

        ctx.strokeStyle = armorBorderColor;
        ctx.lineWidth = 4.5 * s;
        ctx.shadowColor = armorBorderColor;
        // Reduced from 14→8: shadowBlur cost is roughly O(r²), halving saves ~75% GPU on this stroke
        ctx.shadowBlur = (8 * isAwake + 4 * this.sleepProgress) * s;
        ctx.stroke();

        ctx.fillStyle = `rgba(16, 185, 129, ${0.45 * isAwake + 0.15 * this.sleepProgress})`;
        ctx.beginPath();
        ctx.moveTo(fx(12), fy(34 + shockOffsetY));
        ctx.lineTo(fx(32), fy(48 + shockOffsetY));
        ctx.lineTo(fx(30), fy(76 + shockOffsetY));
        ctx.lineTo(fx(20), fy(68 + shockOffsetY));
        ctx.closePath();
        ctx.moveTo(fx(88), fy(34 + shockOffsetY));
        ctx.lineTo(fx(68), fy(48 + shockOffsetY));
        ctx.lineTo(fx(70), fy(76 + shockOffsetY));
        ctx.lineTo(fx(80), fy(68 + shockOffsetY));
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        // 4. Upper Cheek Telemetry Chevrons
        const kbps = (this.netSpeed || 0) / 1024;
        const level = this.isRunning ? (kbps > 2000 ? 3 : (kbps > 400 ? 2 : (kbps > 50 ? 1 : 0))) : 0;

        ctx.save();
        for (let i = 0; i < 3; i++) {
            const isActive = i < level && isAwake > 0.3;
            const glyphAlpha = (isActive ? 0.95 : 0.15) * isAwake + 0.05 * this.sleepProgress;
            // No shadowBlur on chevrons — tiny shapes, cost >> visual benefit.
            // Use pure bright fill for active state instead.
            ctx.fillStyle = isActive ? "#22D3EE" : `rgba(255, 255, 255, ${glyphAlpha})`;
            ctx.shadowColor = "transparent";
            ctx.shadowBlur = 0;

            ctx.beginPath();
            ctx.moveTo(fx(19 + i * 1.5), fy(35 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(23.5 + i * 1.5), fy(35 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(22 + i * 1.5), fy(37.2 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(17.5 + i * 1.5), fy(37.2 + i * 5.2 + shockOffsetY));
            ctx.closePath();
            ctx.fill();

            ctx.beginPath();
            ctx.moveTo(fx(81 - i * 1.5), fy(35 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(76.5 - i * 1.5), fy(35 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(78 - i * 1.5), fy(37.2 + i * 5.2 + shockOffsetY));
            ctx.lineTo(fx(82.5 - i * 1.5), fy(37.2 + i * 5.2 + shockOffsetY));
            ctx.closePath();
            ctx.fill();
        }
        ctx.restore();

        // 5. Active Cooling Turbines (Y = 62)
        const drawTurbine = (tx, ty) => {
            ctx.save();
            ctx.fillStyle = "#090d16";
            ctx.strokeStyle = this.isRunning ? (this.cpu > 80 ? "#EF4444" : "#334155") : "#1e293b";
            ctx.lineWidth = 1.2 * s;
            ctx.beginPath();
            ctx.arc(fx(tx), fy(ty + shockOffsetY), 6.5 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();

            const intakeGlow = isAwake * (this.turbineRPM / 2400) * 10;
            if (intakeGlow > 0.5) {
                ctx.strokeStyle = this.cpu > 80 ? "#EF4444" : accentCyan;
                ctx.shadowColor = ctx.strokeStyle;
                ctx.shadowBlur = intakeGlow * s;
                ctx.lineWidth = 0.8 * s;
                ctx.beginPath();
                ctx.arc(fx(tx), fy(ty + shockOffsetY), 5.8 * s, 0, Math.PI * 2);
                ctx.stroke();
            }

            ctx.save();
            ctx.translate(fx(tx), fy(ty + shockOffsetY));
            ctx.rotate(this.turbineAngle * (tx < 50 ? 1 : -1));
            ctx.strokeStyle = this.isRunning ? (this.cpu > 80 ? "#EF4444" : "#22D3EE") : "#8B5CF6";
            ctx.lineWidth = 1.4 * s;
            for (let b = 0; b < 4; b++) {
                ctx.beginPath();
                ctx.moveTo(0, 0);
                const angle = (b * Math.PI) / 2;
                ctx.lineTo(Math.cos(angle) * 5.0 * s, Math.sin(angle) * 5.0 * s);
                ctx.stroke();
            }
            ctx.restore();

            ctx.fillStyle = "#FFFFFF";
            ctx.beginPath();
            ctx.arc(fx(tx), fy(ty + shockOffsetY), 1.2 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        };

        drawTurbine(22, 62);
        drawTurbine(78, 62);

        // 6. Clean Tinted Visor Screen & Polygonal Cyber Eyes
        ctx.save();
        ctx.fillStyle = "rgba(2, 6, 23, 0.75)";
        ctx.beginPath();
        ctx.moveTo(fx(26), fy(29 + shockOffsetY));
        ctx.lineTo(fx(74), fy(29 + shockOffsetY));
        ctx.lineTo(fx(74), fy(47 + shockOffsetY));
        ctx.lineTo(fx(50), fy(53 + shockOffsetY));
        ctx.lineTo(fx(26), fy(47 + shockOffsetY));
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        const eyeOffsetGx = this.gazeX * 3.5 * s * isAwake;
        const eyeOffsetGy = this.gazeY * 2.5 * s * isAwake + breathe * 0.3;
        const currentAperture = Math.max(0.08, this.eyeOpenness * isAwake);

        ctx.save();
        ctx.fillStyle = this.isRunning ? (this.cpu > 80 ? "#EF4444" : accentCyan) : "#8B5CF6";
        ctx.shadowColor = ctx.fillStyle;
        // Reduced 14→9: eyes are large fills — shadow cost scales with area × blur²
        ctx.shadowBlur = (9 * isAwake + 4 * this.sleepProgress) * s;

        if (currentAperture > 0.18) {
            // Left Sharp Eye
            ctx.beginPath();
            ctx.moveTo(fx(28) + eyeOffsetGx, fy(34 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(43) + eyeOffsetGx, fy(34 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(41) + eyeOffsetGx, fy(34 + shockOffsetY) + 7.2 * s * currentAperture + eyeOffsetGy);
            ctx.lineTo(fx(30) + eyeOffsetGx, fy(34 + shockOffsetY) + 7.2 * s * currentAperture + eyeOffsetGy);
            ctx.closePath();
            ctx.fill();

            // Right Sharp Eye
            ctx.beginPath();
            ctx.moveTo(fx(57) + eyeOffsetGx, fy(34 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(72) + eyeOffsetGx, fy(34 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(70) + eyeOffsetGx, fy(34 + shockOffsetY) + 7.2 * s * currentAperture + eyeOffsetGy);
            ctx.lineTo(fx(59) + eyeOffsetGx, fy(34 + shockOffsetY) + 7.2 * s * currentAperture + eyeOffsetGy);
            ctx.closePath();
            ctx.fill();
        } else {
            // Sleep Standby Slits
            ctx.strokeStyle = this.isRunning ? accentCyan : "#8B5CF6";
            ctx.lineWidth = (2.2 * this.sleepProgress + 1.2 * isAwake) * s;
            ctx.beginPath();
            ctx.moveTo(fx(29) + eyeOffsetGx, fy(38 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(42) + eyeOffsetGx, fy(38 + shockOffsetY) + eyeOffsetGy);
            ctx.moveTo(fx(58) + eyeOffsetGx, fy(38 + shockOffsetY) + eyeOffsetGy);
            ctx.lineTo(fx(71) + eyeOffsetGx, fy(38 + shockOffsetY) + eyeOffsetGy);
            ctx.stroke();
        }
        ctx.restore();

        // 7. Titanium-Clamped Diamond Quantum Arc Reactor
        const breathFreqCore = 0.0018 * isAwake + 0.0008 * this.sleepProgress;
        const glowIntensity = (Math.sin(now * breathFreqCore) * 0.5 + 0.5);
        const coreColor = this.isRunning ? (this.cpu > 80 ? "#EF4444" : signatureEmerald) : "#8B5CF6";
        const centerY = 58;

        ctx.save();
        // Titanium Clamps
        ctx.fillStyle = "#1e293b";
        ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
        ctx.lineWidth = 0.8 * s;
        ctx.beginPath();
        ctx.rect(fx(46), fy(centerY - 17 + shockOffsetY), 8 * s, 3.5 * s);
        ctx.rect(fx(46), fy(centerY + 22 + shockOffsetY), 8 * s, 3.5 * s);
        ctx.fill();
        ctx.stroke();

        // Outer Solid Diamond Shell (Razor Sharp)
        ctx.fillStyle = coreColor;
        ctx.shadowColor = coreColor;
        // Reduced 10+8→7+5; wakeFlash 25→18 (still prominent, just shorter blur radius)
        ctx.shadowBlur = (7 + glowIntensity * 5 * isAwake + this.wakeFlash * 18) * s;
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(centerY - 14 + shockOffsetY));
        ctx.lineTo(fx(64), fy(centerY + shockOffsetY));
        ctx.lineTo(fx(50), fy(centerY + 22 + shockOffsetY));
        ctx.lineTo(fx(36), fy(centerY + shockOffsetY));
        ctx.closePath();
        ctx.fill();

        // Inner Quantum Prism
        ctx.fillStyle = this.isRunning ? (this.cpu > 80 ? "#FFA3A3" : accentCyan) : "#A78BFA";
        ctx.shadowColor = ctx.fillStyle;
        // Reduced 6+6→4+4
        ctx.shadowBlur = (4 + glowIntensity * 4 * isAwake) * s;
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(centerY - 8 + shockOffsetY));
        ctx.lineTo(fx(58), fy(centerY + shockOffsetY));
        ctx.lineTo(fx(50), fy(centerY + 15 + shockOffsetY));
        ctx.lineTo(fx(42), fy(centerY + shockOffsetY));
        ctx.closePath();
        ctx.fill();

        // White Radiant Singularity Heart (Ignition flash on wakeup)
        const heartAlpha = 0.75 + glowIntensity * 0.25 * isAwake + this.wakeFlash * 0.8;
        ctx.fillStyle = `rgba(255, 255, 255, ${Math.min(1.0, heartAlpha)})`;
        ctx.shadowColor = "#FFFFFF";
        // Reduced 8+6→5+4; wakeFlash 20→14
        ctx.shadowBlur = (5 + glowIntensity * 4 * isAwake + this.wakeFlash * 14) * s;
        ctx.beginPath();
        ctx.moveTo(fx(50), fy(centerY - 4 + shockOffsetY));
        ctx.lineTo(fx(54), fy(centerY + shockOffsetY));
        ctx.lineTo(fx(50), fy(centerY + 6 + shockOffsetY));
        ctx.lineTo(fx(46), fy(centerY + shockOffsetY));
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        // 8. Electric Arcs & Click EMP Burst
        if (this.electricArcs.length > 0) {
            ctx.save();
            for (const arc of this.electricArcs) {
                ctx.strokeStyle = arc.color;
                ctx.lineWidth = 1.5 * s;
                ctx.shadowColor = arc.color;
                ctx.shadowBlur = 8 * s;
                ctx.globalAlpha = Math.max(0, arc.life);
                ctx.beginPath();
                ctx.moveTo(fx(arc.fromX), fy(arc.fromY + shockOffsetY));
                const midX = (arc.fromX + arc.toX) / 2 + (Math.random() - 0.5) * 8;
                const midY = (arc.fromY + arc.toY) / 2 + (Math.random() - 0.5) * 8;
                ctx.lineTo(fx(midX), fy(midY + shockOffsetY));
                ctx.lineTo(fx(arc.toX), fy(arc.toY + shockOffsetY));
                ctx.stroke();
            }
            ctx.restore();
        }

        if (this.shockParticles.length > 0) {
            ctx.save();
            // Set shadowBlur once for all particles — avoids per-particle Gaussian raster pass
            ctx.shadowBlur = 6 * s;
            for (const p of this.shockParticles) {
                ctx.fillStyle = p.color;
                ctx.shadowColor = p.color;
                ctx.globalAlpha = Math.max(0, p.life);
                ctx.beginPath();
                ctx.arc(fx(p.x), fy(p.y), p.size * s, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.restore();
        }

        ctx.restore();
    }
}
