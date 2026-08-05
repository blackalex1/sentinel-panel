import { apiFetch } from "./api.js";

function safeGetLang() {
    try {
        return localStorage.getItem("panel_lang") || "ru";
    } catch (e) {
        console.warn("Failed to get language from localStorage:", e);
        return "ru";
    }
}

function safeSetLang(langCode) {
    try {
        localStorage.setItem("panel_lang", langCode);
    } catch (e) {
        console.warn("Failed to save language to localStorage:", e);
    }
}

export let currentLang = safeGetLang();
export let translations = {};

/**
 * Инициализирует мультиязычность:
 * 1. Получает список доступных языков с бэкенда.
 * 2. Рендерит селектор выбора языка.
 * 3. Загружает словарь для текущего языка и переводит страницу.
 */
export async function initI18n() {
    try {
        // 1. Запрос списка доступных языков
        const langRes = await apiFetch("/api/locales");
        if (langRes && langRes.success) {
            renderLanguageSelector(langRes.obj);
        }
        
        // 2. Загружаем словарь для текущего выбранного языка
        await loadLanguage(currentLang);
        
    } catch (e) {
        console.error("[i18n] Initialization failed:", e);
    }
}

/**
 * Динамически рендерит опции выбора языка
 */
function renderLanguageSelector(languages) {
    const select = document.getElementById("lang-select");
    if (!select) return;
    
    select.innerHTML = "";
    languages.forEach(lang => {
        const option = document.createElement("option");
        option.value = lang.code;
        option.text = lang.name;
        if (lang.code === currentLang) {
            option.selected = true;
        }
        select.appendChild(option);
    });
    
    // Снимаем старый листенер и вешаем новый
    select.onchange = async (e) => {
        const newLang = e.target.value;
        await changeLanguage(newLang);
    };
}

/**
 * Переключает текущий язык, сохраняет его в localStorage и переводит UI
 */
export async function changeLanguage(langCode) {
    currentLang = langCode;
    safeSetLang(langCode);
    
    // Загружаем перевод и переводим страницу
    const success = await loadLanguage(langCode);
    if (success) {
        window.dispatchEvent(new CustomEvent("show-toast", {
            detail: {
                text: currentLang === "ru" ? "Язык изменен на Русский" : "Language changed to English"
            }
        }));
        
        // Также синхронизируем выбор языка с настройками профиля на бэкенде
        try {
            const settingsRes = await apiFetch("/api/settings");
            if (settingsRes && settingsRes.success) {
                await apiFetch("/api/settings/update", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        secret_path: settingsRes.secret_path,
                        decoy_type: settingsRes.decoy_type,
                        decoy_value: settingsRes.decoy_value,
                        block_torrent: settingsRes.block_torrent,
                        block_advertisers: settingsRes.block_advertisers,
                        route_chatgpt_warp: settingsRes.route_chatgpt_warp,
                        ssl_domain: settingsRes.ssl_domain,
                        ssl_email: settingsRes.ssl_email,
                        language: langCode
                    })
                });
            }
        } catch (e) {
            console.error("[i18n] Failed to sync language setting to backend:", e);
        }
    }
}

/**
 * Скачивает с сервера JSON словарь перевода и вызывает транслятор страницы
 */
async function loadLanguage(langCode) {
    try {
        const res = await apiFetch(`/api/locales/${langCode}`);
        if (res && res.success) {
            translations = res.obj;
            translatePage();
            return true;
        }
    } catch (e) {
        console.error(`[i18n] Failed to load language ${langCode}:`, e);
    }
    return false;
}

/**
 * Переводчик по ключу. Если ключ отсутствует, возвращает fallback или сам ключ
 */
export function t(key, fallback = "") {
    if (translations && translations[key]) {
        return translations[key];
    }
    return fallback || key;
}

/**
 * Переводит все элементы текущей страницы с data-i18n, data-i18n-placeholder и data-i18n-title
 */
export function translatePage() {
    // 1. Текстовое содержимое (textContent)
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (translations[key]) {
            // Если внутри элемента есть иконки (<i> или <svg>), сохраняем их и меняем только текст
            const icon = el.querySelector("i, svg");
            if (icon) {
                // Очищаем текстовые ноды, оставляя иконку
                el.childNodes.forEach(node => {
                    if (node.nodeType === 3) {
                        node.textContent = "";
                    }
                });
                // Добавляем переведенный текст после иконки
                el.appendChild(document.createTextNode(" " + translations[key]));
            } else {
                el.textContent = translations[key];
            }
        }
    });

    // 2. Плейсхолдеры полей ввода (placeholder)
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        const key = el.getAttribute("data-i18n-placeholder");
        if (translations[key]) {
            el.placeholder = translations[key];
        }
    });

    // 3. Всплывающие подсказки кнопок (title)
    document.querySelectorAll("[data-i18n-title]").forEach(el => {
        const key = el.getAttribute("data-i18n-title");
        if (translations[key]) {
            el.title = translations[key];
        }
    });
}
