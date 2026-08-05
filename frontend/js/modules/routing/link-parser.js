export function parseProxyLink(link) {
    if (!link) return null;
    link = link.trim();
    
    function safeAtob(str) {
        str = str.trim();
        str = str.split('?')[0].split('/')[0];
        str = str.replace(/-/g, '+').replace(/_/g, '/');
        while (str.length % 4) {
            str += '=';
        }
        try {
            return atob(str);
        } catch (e) {
            return null;
        }
    }
    
    if (link.startsWith("vless://")) {
        const withoutScheme = link.substring(8);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remark = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";
        
        // Split by ? first to isolate query string from userinfo and host/port
        const qSplit = mainPart.split('?');
        const credentialsAndHost = qSplit[0];
        const queryString = qSplit[1] || "";
        
        const atIndex = credentialsAndHost.indexOf('@');
        if (atIndex === -1) return null;
        const uuid = credentialsAndHost.substring(0, atIndex);
        const hostPort = credentialsAndHost.substring(atIndex + 1);
        
        const hpSplit = hostPort.split(':');
        const host = hpSplit[0];
        const port = hpSplit[1] ? parseInt(hpSplit[1]) : "";
        
        const params = new URLSearchParams(queryString);
        const security = params.get("security") || "none";
        const sni = params.get("sni") || "";
        const pbk = params.get("pbk") || "";
        const sid = params.get("sid") || params.get("shortId") || "";
        const fp = params.get("fp") || "chrome";
        const flow = params.get("flow") || "";
        const alpn = params.get("alpn") || "";
        const encryption = params.get("encryption") || "";
        const pinSHA256 = params.get("pinSHA256") || params.get("pinnedPeerCertSha256") || "";
        const spx = params.get("spx") || params.get("spiderX") || "";
        
        return {
            protocol: "vless",
            remark,
            host,
            port,
            uuid,
            security,
            sni,
            pbk,
            sid,
            fp,
            flow,
            alpn,
            encryption,
            pinSHA256,
            spx
        };
    }
    
    if (link.startsWith("hysteria2://") || link.startsWith("hysteria://") || link.startsWith("hy2://")) {
        const isHysteria2 = link.startsWith("hysteria2://") || link.startsWith("hy2://");
        const schemeLen = link.startsWith("hysteria2://") ? 12 : (link.startsWith("hysteria://") ? 11 : 6);
        const withoutScheme = link.substring(schemeLen);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remark = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";
        
        // Split by ? first to isolate query string
        const qSplit = mainPart.split('?');
        const credentialsAndHost = qSplit[0];
        const queryString = qSplit[1] || "";
        
        let auth = "";
        let hostPort = credentialsAndHost;
        const atIndex = credentialsAndHost.indexOf('@');
        if (atIndex !== -1) {
            auth = credentialsAndHost.substring(0, atIndex);
            hostPort = credentialsAndHost.substring(atIndex + 1);
        }
        
        const hpSplit = hostPort.split(':');
        const host = hpSplit[0];
        const port = hpSplit[1] ? parseInt(hpSplit[1]) : (isHysteria2 ? 443 : "");
        
        const params = new URLSearchParams(queryString);
        const sni = params.get("sni") || params.get("peer") || "";
        const alpn = params.get("alpn") || "h3";
        
        let up = params.get("up") || "";
        let down = params.get("down") || "";
        if (up) up = parseInt(up);
        if (down) down = parseInt(down);
        
        // Insecure (allowInsecure)
        const insecure = params.get("insecure") === "1" || params.get("insecure") === "true" || params.get("allowInsecure") === "1" || params.get("allowInsecure") === "true";
        
        // Obfuscation (obfs / obfs-password)
        const obfs = params.get("obfs") || "";
        const obfsPassword = params.get("obfs-password") || params.get("obfs_password") || params.get("obfsPassword") || "";
        
        const pinSHA256 = params.get("pinSHA256") || params.get("pinnedPeerCertSha256") || "";
        const hop = params.get("hop") || params.get("mport") || params.get("ports") || "";
        
        return {
            protocol: "hysteria2",
            remark,
            host,
            port: hop || port,
            hop,
            mport: hop,
            ports: hop,
            password: decodeURIComponent(auth),
            sni,
            alpn,
            up,
            down,
            insecure,
            obfs,
            obfsPassword,
            pinSHA256
        };
    }
    
    if (link.startsWith("socks://") || link.startsWith("socks5://") || link.startsWith("http://")) {
        const isSocks5 = link.startsWith("socks5://");
        const isSocks = link.startsWith("socks://");
        const isHttp = link.startsWith("http://");
        const schemeLen = isSocks5 ? 9 : (isSocks ? 8 : 7);
        
        const withoutScheme = link.substring(schemeLen);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remark = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";
        
        // Split by ? first to isolate query string
        const qSplit = mainPart.split('?');
        const credentialsAndHost = qSplit[0];
        
        let userPass = "";
        let hostPort = credentialsAndHost;
        const atIndex = credentialsAndHost.indexOf('@');
        if (atIndex !== -1) {
            userPass = credentialsAndHost.substring(0, atIndex);
            hostPort = credentialsAndHost.substring(atIndex + 1);
        }
        
        const hpSplit = hostPort.split(':');
        const host = hpSplit[0];
        const port = hpSplit[1] ? parseInt(hpSplit[1]) : "";
        
        let username = "";
        let password = "";
        if (userPass) {
            const upSplit = userPass.split(':');
            username = upSplit[0] || "";
            password = upSplit[1] || "";
        }
        
        return {
            protocol: isHttp ? "http" : "socks",
            remark,
            host,
            port,
            username,
            password
        };
    }
    
    if (link.startsWith("ss://")) {
        const withoutScheme = link.substring(5);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remark = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";
        
        // Split by ? first to isolate query string
        const qSplit = mainPart.split('?');
        const credentialsAndHost = qSplit[0];
        
        let method = "";
        let password = "";
        let host = "";
        let port = "";
        
        if (credentialsAndHost.includes('@')) {
            const atIndex = credentialsAndHost.lastIndexOf('@');
            const userinfoBase64 = credentialsAndHost.substring(0, atIndex);
            const hostPort = credentialsAndHost.substring(atIndex + 1);
            
            const userinfo = safeAtob(userinfoBase64);
            if (userinfo) {
                const upSplit = userinfo.split(':');
                method = upSplit[0] || "";
                password = upSplit[1] || "";
            }
            
            const hpSplit = hostPort.split(':');
            host = hpSplit[0] || "";
            port = hpSplit[1] ? parseInt(hpSplit[1]) : "";
        } else {
            const decoded = safeAtob(credentialsAndHost);
            if (decoded && decoded.includes('@')) {
                const atIndex = decoded.lastIndexOf('@');
                const userinfo = decoded.substring(0, atIndex);
                const upSplit = userinfo.split(':');
                method = upSplit[0] || "";
                password = upSplit[1] || "";
                
                const hostPort = decoded.substring(atIndex + 1);
                const hpSplit = hostPort.split(':');
                host = hpSplit[0] || "";
            }
        }
        
        if (host && port) {
            return {
                protocol: "shadowsocks",
                remark,
                host,
                port,
                password,
                method
            };
        }
    }
        
    if (link.startsWith("trojan://")) {
        const withoutScheme = link.substring(9);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remark = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";
        
        const qSplit = mainPart.split('?');
        const credentialsAndHost = qSplit[0];
        const queryString = qSplit[1] || "";
        
        const atIndex = credentialsAndHost.indexOf('@');
        if (atIndex === -1) return null;
        const password = credentialsAndHost.substring(0, atIndex);
        const hostPort = credentialsAndHost.substring(atIndex + 1);
        
        const hpSplit = hostPort.split(':');
        const host = hpSplit[0];
        const port = hpSplit[1] ? parseInt(hpSplit[1]) : 443;
        
        const params = new URLSearchParams(queryString);
        const security = params.get("security") || "tls";
        const sni = params.get("sni") || params.get("peer") || "";
        const alpn = params.get("alpn") || "";
        const fp = params.get("fp") || "chrome";
        const type = params.get("type") || "tcp";
        const path = params.get("path") || "/";
        const hostHeader = params.get("host") || "";

        return {
            protocol: "trojan",
            remark,
            host,
            port,
            password: decodeURIComponent(password),
            security,
            sni,
            alpn,
            fp,
            type,
            path,
            hostHeader
        };
    }

    if (link.startsWith("vmess://")) {
        const withoutScheme = link.substring(8);
        const hashSplit = withoutScheme.split('#');
        const mainPart = hashSplit[0];
        const remarkFromHash = hashSplit[1] ? decodeURIComponent(hashSplit[1]) : "";

        let decodedStr = safeAtob(mainPart);
        if (!decodedStr) return null;

        try {
            const vObj = JSON.parse(decodedStr);
            return {
                protocol: "vmess",
                remark: remarkFromHash || vObj.ps || "",
                host: vObj.add || "",
                port: vObj.port ? parseInt(vObj.port) : 443,
                uuid: vObj.id || "",
                alterId: vObj.aid !== undefined ? parseInt(vObj.aid) : 0,
                security: vObj.scy || "auto",
                network: vObj.net || "tcp",
                path: vObj.path || "/",
                hostHeader: vObj.host || "",
                tls: vObj.tls || "none",
                sni: vObj.sni || "",
                alpn: vObj.alpn || ""
            };
        } catch (e) {
            return null;
        }
    }

    return null;
}
