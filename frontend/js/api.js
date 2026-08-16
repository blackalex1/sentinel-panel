import { showToast } from "./ui.js";
import { t } from "./i18n.js";

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
            return null;
        }
        return await response.json();
    } catch (error) {
        // Suppress benign network aborts and transient connection errors during polling/reload
        if (error && (error.name === "AbortError" || error.name === "TypeError")) {
            return null;
        }
        console.error("API error:", error);
        if (!url.includes("csrf-token") && !url.includes("status")) {
            showToast(t("api_connection_error", "Ошибка соединения с API"), "error");
        }
        return null;
    }
}
