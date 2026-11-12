from .params import (
    detect_best_engine,
    extract_common_outbound_params,
    parse_json_or_dict,
)
from .singbox import build_singbox_outbound
from .xray import _build_xray_stream_settings, build_xray_outbound


def build_outbound_config(
    engine: str,
    protocol: str,
    settings: dict,
    stream_settings: dict = None,
    tag: str = "test-out",
) -> dict:
    """Универсальный фасад адаптации исходящего подключения под указанное ядро."""
    engine_norm = detect_best_engine(protocol, engine)
    if engine_norm == "sing-box":
        return build_singbox_outbound(protocol, settings, stream_settings, tag)
    return build_xray_outbound(protocol, settings, stream_settings, tag)


__all__ = [
    "parse_json_or_dict",
    "detect_best_engine",
    "extract_common_outbound_params",
    "build_singbox_outbound",
    "_build_xray_stream_settings",
    "build_xray_outbound",
    "build_outbound_config",
]
