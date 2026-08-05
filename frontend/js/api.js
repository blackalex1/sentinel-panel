import { showToast } from "./ui.js";

let csrfToken = "";

export function getCsrfToken() {
    return csrfToken;
}

export function setCsrfToken(token) {
    csrfToken = token;
}

export async function apiFetch(url, options = {}) {
    const headers = options.headers || {};
    if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
    }
    
    options.headers = headers;
    
    try {
        const response = await fetch(url, options);
        if (response.status === 404) {
            // Decoy 404 handler
            if (!url.includes("csrf-token")) {
                location.reload();
            }
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error("API error:", error);
        showToast("Ошибка соединения с API", "error");
        return null;
    }
}
