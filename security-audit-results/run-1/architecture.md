# Architecture Mapping

## 1. Application Overview
**Spectre Panel** is a stealth VPN Web Control Panel and orchestration suite designed to bypass internet censorship. It manages two core VPN engines: **Xray** and **Hysteria 2**.
- **Type**: FastAPI Web Application (with Master-Edge architecture) + Host Agent Daemon + Telegram Bot.
- **Actors**:
  - **Administrator**: Full privileges to manage clients, configurations, nodes, backups, and system optimizations.
  - **Edge Nodes**: Authenticated servers that fetch VPN configurations and report client traffic metrics back to the Master panel.
  - **VPN Clients**: Read-only access to download their personal proxy subscription profiles.

## 2. Technology Stack
- **Backend**: Python 3 (FastAPI, Uvicorn, SQLAlchemy).
- **Database**: SQLite (default local) or PostgreSQL.
- **Frontend**: Plain HTML5, CSS3, Vanilla ES6 JS Modules.
- **VPN Runtimes**: Precompiled binary files of `xray` and `hysteria` placed in the `bin/` directory.
- **Host Integration**: Isolated `host_agent.py` daemon communicating with the FastAPI container via Unix Domain Socket at `/var/run/spectre/agent.sock` to execute system optimizations (BBR, WARP, iptables).

## 3. Trust Boundaries & Access Control
- **Authentication**:
  - Administrative routes are gated behind secure cookie sessions (using cryptographically secure session IDs stored in SQLite/Postgre database) or Bearer Token API credentials (for bot-controller).
  - Edge Nodes authenticate using API tokens hashed via SHA-256 and matched via `hmac.compare_digest`.
  - Telegram Mini App interface uses WebApp signature validation via HMAC-SHA256 (bot token used as HMAC key) with a 24-hour expiration window.
- **Authorization**:
  - Mutating operations (`POST`, `PUT`, `DELETE`) are guarded against Cross-Site Request Forgery (CSRF) by matching header `X-CSRF-Token` against database-stored tokens linked to session IDs.
- **Privilege Separation**:
  - The FastAPI container runs with low privileges and delegates host-level configurations (like loading kernel BBR modules or iptables rules) to the host agent socket, keeping container breakouts contained.

## 4. Input Surface Inventory
- **Network-Facing APIs**:
  - `/login` & `/api/logout`: Session creation and disposal. Protected by database-backed login attempt rate limits.
  - `/api/system/backup/download` & `/api/system/backup/upload`: Database configurations backup import/export.
  - `/api/ssl/generate`: Requests Let's Encrypt SSL certificates (ACME HTTP-01 flow on port 80).
  - `/api/node/join` & `/api/node/report`: API endpoints for node orchestration.
  - `/sub/{client_uuid}`: Public endpoint allowing VPN clients to query VLESS/Hysteria subscription details.
- **Sinks and Command Executions**:
  - `subprocess.run` & `subprocess.Popen` are used to launch cores (`xray.exe`, `hysteria`) and configure iptables. These invocations are executed as lists without `shell=True` to prevent shell injection.
  - Database writes use SQLAlchemy query parameters by default, preventing SQL injections.
  - Decoy static files rendering utilizes relative path verification (`relative_to`) to prevent path traversal.
  - Core download URLs are parsed and restricted to official `https://github.com` release paths for the respective repositories to prevent SSRF and malicious package execution.

## 5. Main Entry Points
- Web Application Main Server: [backend/main.py](file:///c:/Users/black/PycharmProjects/panel/backend/main.py)
- Web API Routers: [backend/api.py](file:///c:/Users/black/PycharmProjects/panel/backend/api.py)
- Host Agent Daemon: [host/host_agent.py](file:///c:/Users/black/PycharmProjects/panel/host/host_agent.py)
- Telegram Bot: [bot/mini_bot.py](file:///c:/Users/black/PycharmProjects/panel/bot/mini_bot.py)
- Decoy & Static file renderer: [backend/auth_utils.py](file:///c:/Users/black/PycharmProjects/panel/backend/auth_utils.py)
