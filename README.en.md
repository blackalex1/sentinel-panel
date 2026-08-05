<div align="center">

[![Telegram](https://img.shields.io/badge/Telegram-Join%20Chat-26A5E4?logo=telegram&logoColor=white)](https://t.me/spectre_panel)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?logo=open-source-initiative&logoColor=white)](LICENSE)
[![Latest Release](https://img.shields.io/badge/Release-Latest-brightgreen?logo=github)](https://github.com/blackalex1/Spectre-panel/releases)
[![Language](https://img.shields.io/badge/Language-Russian-009688?logo=google-translate&logoColor=white)](README.md)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red)](#)

# 🚀 Spectre Panel

</div>

**Spectre Panel** is a modern, high-performance, and stealth VPN web control panel designed to bypass internet censorship. It integrates the power of **Xray** and **Hysteria 2** cores with a user-friendly web interface, rich visual effects, and extensive automation capabilities.

---

## 📋 Quick Start Guide (One-Click Installation)

To automatically install dependencies, configure cores, and launch the panel, run the following command:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ReturnFI/spectre-panel/main/installation/install_with_docker.sh)
```

> [!NOTE]
> The installation script will automatically install Docker, set up system services, generate secure random passwords/secret path, and output your login credentials card.

---

## 💎 Features

* **Xray Core**: Support for VLESS (with classical `X25519` and post-quantum `ML-KEM-768` Reality key exchanges), VMess, Trojan, ShadowSocks, SOCKS5 protocols.
* **Hysteria 2 Core**: High-speed QUIC-based protocol supporting Masquerade and Obfuscation (Salamander) modes.
* **Stealth Masking (Decoy)**: Protects your admin panel from scans by showing a decoy page (Nginx 404, landing page, proxying, or redirect) on root requests.
* **Outbound Routing**: Direct PASTE proxy link import from clipboard, real-time TCP ping latency checks, and HTTP transit proxy tests.
* **Quota Management**: Blocks clients automatically upon exceeding traffic limits, subscription expiration, or concurrent IP limits.
* **Telegram Integration**: Automated block notifications and full panel management via built-in Telegram WebApp (Mini App).
* **Security**: Two-Factor Authentication (2FA/TOTP) support to secure admin accounts.
* **Additional features**: Cloudflare WARP integration, Let's Encrypt SSL Certbot auto-generation, and automated database backups to Telegram.

## 🚀 Installation & Launch

The panel runs in Docker containers and interacts with the host-agent (a system service on the server).

### 📋 One-Click Automatic Installation (Recommended)
To automatically install Docker, configure system services, and start Spectre Panel:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/blackalex1/Spectre-panel/main/installation/install_with_docker.sh)
```

### 🐳 Build from Local Repository
To build and run the panel from local source files:

```bash
git clone https://github.com/blackalex1/Spectre-panel.git && cd Spectre-panel && docker compose up -d --build
```
To view the secret path, port, and token generated on initial startup:
```bash
docker compose logs vpn-panel
```

---

## 🧪 Testing

For local development and testing:
```bash
TEST_DATABASE_URL="sqlite:///test_panel.db" TEST_DATABASE_ADMIN_URL="sqlite:///test_panel.db" .venv/bin/pytest
```
