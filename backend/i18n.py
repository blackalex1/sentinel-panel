import json
import logging
from pathlib import Path
from backend.config import BASE_DIR

_translations = {}

def load_translations():
    """Сканирует папку locales/ и загружает все JSON словари локализации"""
    global _translations
    _translations.clear()
    
    locales_dir = BASE_DIR / "locales"
    if not locales_dir.exists():
        logging.warning(f"[i18n] locales directory not found at: {locales_dir}")
        return
        
    for path in locales_dir.glob("*.json"):
        lang = path.stem.lower()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Простейшая валидация структуры
                if "meta" in data and "name" in data["meta"]:
                    _translations[lang] = data
                    logging.info(f"[i18n] Loaded translation for '{lang}' ({data['meta']['name']})")
                else:
                    logging.warning(f"[i18n] Invalid translation format in {path.name} (missing meta.name)")
        except Exception as e:
            logging.error(f"[i18n] Failed to load translation from {path}: {e}")

def get_available_languages() -> list[dict]:
    """Возвращает список всех доступных в системе языков с их названиями"""
    languages = []
    for code, data in _translations.items():
        languages.append({
            "code": code,
            "name": data["meta"]["name"]
        })
    # Сортируем: Русский и English первыми, остальные по имени
    languages.sort(key=lambda x: (x["code"] != "ru", x["code"] != "en", x["name"]))
    return languages

def t(key: str, lang: str = "ru", category: str = "backend", **kwargs) -> str:
    """
    Возвращает переведенную строку по ключу, категории и языку.
    Поддерживает подстановку именованных аргументов (например, count=3).
    Если перевод отсутствует, делает фолбек на русский язык, затем на сам ключ.
    """
    if not lang:
        lang = "ru"
    lang = lang.lower()
    
    # 1. Пытаемся взять из запрошенного языка
    lang_dict = _translations.get(lang)
    if not lang_dict:
        # Пытаемся взять по дефолту на русском
        lang_dict = _translations.get("ru", {})
        
    cat_dict = lang_dict.get(category, {})
    val = cat_dict.get(key)
    
    # 2. Если нет значения, делаем явный фолбек на русский
    if val is None and lang != "ru":
        val = _translations.get("ru", {}).get(category, {}).get(key)
        
    # 3. Если всё еще нет, возвращаем сам ключ
    if val is None:
        return key
        
    # 4. Подставляем переданные форматируемые параметры
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception as e:
            logging.error(f"[i18n] Format error for key '{key}' in lang '{lang}': {e}")
            
    return val

# Загружаем при импорте модуля
load_translations()
