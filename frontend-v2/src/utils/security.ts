/**
 * Security & Input Validation Utilities
 * Prevents XSS, command injection, and payload corruption.
 */

export function sanitizeString(input: string): string {
  if (!input) return '';
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

export function isValidPort(port: number | string): boolean {
  const p = Number(port);
  return !isNaN(p) && p >= 1 && p <= 65535;
}

export function isValidIP(ip: string): boolean {
  if (!ip) return false;
  const ipv4Regex = /^([0-9]{1,3}\.){3}[0-9]{1,3}$/;
  const ipv6Regex = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$/;
  return ipv4Regex.test(ip.trim()) || ipv6Regex.test(ip.trim());
}

export function validateAllowedIPs(ipsStr: string): { valid: boolean; error?: string } {
  if (!ipsStr || !ipsStr.trim()) return { valid: true };
  const list = ipsStr.split(',').map((s) => s.trim()).filter(Boolean);
  for (const item of list) {
    // Check IPv4/IPv6 or CIDR notation
    const parts = item.split('/');
    if (parts.length > 2) return { valid: false, error: `Invalid CIDR: ${item}` };
    if (!isValidIP(parts[0])) return { valid: false, error: `Invalid IP address: ${item}` };
    if (parts.length === 2) {
      const mask = Number(parts[1]);
      if (isNaN(mask) || mask < 0 || mask > 128) return { valid: false, error: `Invalid subnet mask: ${item}` };
    }
  }
  return { valid: true };
}

export function generateRandomPassword(length = 16): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  const randomValues = new Uint8Array(length);
  window.crypto.getRandomValues(randomValues);
  for (let i = 0; i < length; i++) {
    result += chars[randomValues[i] % chars.length];
  }
  return result;
}
