<div align="center">

[![License](https://img.shields.io/badge/License-MIT-blue.svg?logo=open-source-initiative&logoColor=white)](LICENSE)
[![Latest Release](https://img.shields.io/badge/Release-Latest-brightgreen?logo=github)](https://github.com/blackalex1/Spectre-panel/releases)
[![Language](https://img.shields.io/badge/Language-English-009688?logo=google-translate&logoColor=white)](README.en.md)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red)](#)

# 🚀 Spectre Panel

</div>

**Spectre Panel** — это современная, быстрая и незаметная (Stealth) веб-панель управления серверами VPN для обхода блокировок. Проект объединяет мощь ядер **Xray** и **Hysteria 2** с удобным веб-интерфейсом, богатыми визуальными эффектами и широкими возможностями автоматизации.

---

## 📋 Быстрый старт

Для автоматической установки зависимостей, настройки ядра и запуска панели выполните команду:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/ReturnFI/spectre-panel/main/installation/install_with_docker.sh)
```

> [!NOTE]
> Скрипт сам установит Docker, настроит системные службы, сгенерирует безопасные пароли/секретный путь доступа и выведет готовую карточку с реквизитами для входа в панель.

---

## 💎 Возможности

* **Ядро Xray**: Поддержка протоколов VLESS (сReality классическим X25519 и пост-квантовым `ML-KEM-768` шифрованием), VMess, Trojan, ShadowSocks, SOCKS5.
* **Ядро Hysteria 2**: Сверхскоростной протокол на базе QUIC с поддержкой Маскировки (Masquerade) и Обфускации (Salamander).
* **Скрытность (Stealth)**: Маскировка веб-панели (Decoy) под Nginx 404, сайт-визитку, проксирование или редирект для защиты от сканирования.
* **Маршрутизация**: Проверка пинга (TCP) и транзита (HTTP) для исходящих подключений, автоимпорт прокси-ссылок из буфера обмена.
* **Управление лимитами**: Блокировка клиентов по трафику, сроку действия или лимиту одновременно используемых IP-адресов.
* **Telegram Bot**: Уведомления об автоблокировках клиентов и полноценное управление через встроенный Telegram WebApp (Mini App).
* **Безопасность**: Защита входа с помощью двухфакторной аутентификации (2FA/TOTP).
* **Дополнительно**: Интеграция с Cloudflare WARP, автоматический выпуск Let's Encrypt SSL-сертификатов и регулярные бэкапы БД в Telegram.

## 🚀 Установка и Запуск

Панель работает в Docker-контейнерах и взаимодействует с хост-агентом (системной службой на сервере).

### 📋 Автоматическая установка (Рекомендуется)
Для автоматической установки Docker, настройки системных служб и запуска Spectre Panel выполните одну команду:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/blackalex1/Spectre-panel/main/installation/install_with_docker.sh)
```

### 🐳 Сборка из локального репозитория
Для сборки и запуска панели из локальных исходных файлов:

```bash
git clone https://github.com/blackalex1/Spectre-panel.git && cd Spectre-panel && docker compose up -d --build
```
Для просмотра сгенерированного при первом старте секретного пути доступа, порта и токена:
```bash
docker compose logs vpn-panel
```

---

## 🧪 Тестирование

Для локального тестирования и отладки:
```bash
TEST_DATABASE_URL="sqlite:///test_panel.db" TEST_DATABASE_ADMIN_URL="sqlite:///test_panel.db" .venv/bin/pytest
```
