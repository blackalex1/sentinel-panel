#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - DNS Resolver & Bootstrap Module
# ==============================================================================

# Ensure standard unencrypted DNS resolution (UDP 53) without DoH blocking
ensure_unencrypted_dns() {
    local RESOLVE_OK=0

    # 1. Quick check if github.com resolves via system
    if command -v getent &>/dev/null && getent hosts github.com &>/dev/null; then
        RESOLVE_OK=1
    elif command -v nslookup &>/dev/null && nslookup github.com &>/dev/null; then
        RESOLVE_OK=1
    elif command -v python3 &>/dev/null && python3 -c "import socket; socket.gethostbyname('github.com')" &>/dev/null; then
        RESOLVE_OK=1
    elif command -v curl &>/dev/null && curl -s --connect-timeout 2 -I https://github.com &>/dev/null; then
        RESOLVE_OK=1
    fi

    if [ "$RESOLVE_OK" -eq 1 ]; then
        return 0
    fi

    log_warn "Системный DNS не смог разрешить github.com (возможно заблокирован DoH/DoT)."
    log_info "Переключение на стандартный нешифрованный DNS (8.8.8.8, 1.1.1.1, 8.8.4.4, UDP:53)..."

    if [ "$EUID" -eq 0 ] && [ -w "/etc/resolv.conf" ]; then
        [ ! -f "/etc/resolv.conf.sentinel.bak" ] && cp -L /etc/resolv.conf /etc/resolv.conf.sentinel.bak 2>/dev/null || true

        if command -v resolvectl &>/dev/null; then
            resolvectl dnsovertls no 2>/dev/null || true
            resolvectl dns 8.8.8.8 1.1.1.1 8.8.4.4 2>/dev/null || true
        fi

        cat << 'EOF' > /tmp/resolv.conf.sentinel
nameserver 8.8.8.8
nameserver 1.1.1.1
nameserver 8.8.4.4
options timeout:2 attempts:2
EOF
        if [ -f "/etc/resolv.conf" ]; then
            grep -E '^(search|domain)' /etc/resolv.conf >> /tmp/resolv.conf.sentinel 2>/dev/null || true
            cp -f /tmp/resolv.conf.sentinel /etc/resolv.conf 2>/dev/null || true
            rm -f /tmp/resolv.conf.sentinel
        fi

        if command -v python3 &>/dev/null && python3 -c "import socket; socket.gethostbyname('github.com')" &>/dev/null; then
            log_success "DNS успешно переведен на стандартный нешифрованный режим (UDP:53). github.com доступен!"
            return 0
        fi
    fi

    # Fallback: direct unencrypted DNS socket query via python
    if command -v python3 &>/dev/null; then
        local GH_IP
        GH_IP=$(python3 -c "
import socket
def query_dns(domain, dns_server='8.8.8.8'):
    packet = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
    for part in domain.split('.'):
        packet += bytes([len(part)]) + part.encode('ascii')
    packet += b'\x00\x00\x01\x00\x01'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.5)
    sock.sendto(packet, (dns_server, 53))
    data, _ = sock.recvfrom(1024)
    sock.close()
    if len(data) > 12:
        for i in range(len(data) - 4):
            if data[i:i+2] == b'\x00\x01' and data[i+2:i+4] == b'\x00\x01':
                ip = socket.inet_ntoa(data[-4:])
                return ip
    return ''

for s in ['8.8.8.8', '1.1.1.1', '8.8.4.4', '9.9.9.9']:
    try:
        ip = query_dns('github.com', s)
        if ip and not ip.startswith('127.'):
            print(ip)
            break
    except Exception:
        continue
" 2>/dev/null || true)
        if [ -n "$GH_IP" ] && [ "$EUID" -eq 0 ] && [ -w "/etc/hosts" ]; then
            log_success "Разрешен IP github.com через прямой UDP DNS ($GH_IP). Запись в /etc/hosts..."
            sed -i '/github.com/d' /etc/hosts 2>/dev/null || true
            echo "$GH_IP github.com api.github.com raw.githubusercontent.com" >> /etc/hosts
        fi
    fi
}
