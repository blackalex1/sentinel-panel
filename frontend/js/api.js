
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
            window.dispatchEvent(new CustomEvent("show-toast", { detail: { key: "api_connection_error", fallback: "Ошибка соединения с API", type: "error" } }));
        }
        return null;
    }
}
