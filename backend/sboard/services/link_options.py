"""Options shared by URI import, link export and Mihomo compatibility checks."""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import parse_qs


def certificate_pin(value: str) -> str:
    """Accept the hex URI format and Xray/3x-ui's base64 SHA-256 format."""
    compact = value.replace(":", "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", compact):
        return compact.lower()
    try:
        decoded = base64.b64decode(value, validate=True)
    except ValueError:
        decoded = b""
    if len(decoded) == 32:
        return decoded.hex()
    raise ValueError("certificate pin must be a SHA-256 hex or base64 fingerprint")


def validate_finalmask(value: Any) -> None:
    if not isinstance(value, dict):
        # Used from Pydantic validators, which require ValueError.
        raise ValueError("fm (FinalMask) must be a JSON object")  # noqa: TRY004
    for key in ("tcp", "udp"):
        if key in value and (
            not isinstance(value[key], list)
            or any(not isinstance(mask, dict) for mask in value[key])
        ):
            raise ValueError(f"fm.{key} must be an array of objects")
    if "quicParams" in value and not isinstance(value["quicParams"], dict):
        raise ValueError("fm.quicParams must be an object")


def ss_plugin_options(extra: dict[str, Any]) -> dict[str, Any]:
    """Convert SIP002's plugin string; retain the original query for link export."""
    query = parse_qs(extra.get("plugin_query") or "")
    plugin = query.get("plugin", [""])[0]
    if not plugin:
        return {}
    name, *parts = plugin.split(";")
    options = dict(part.split("=", 1) if "=" in part else (part, True) for part in parts if part)
    if name in {"obfs-local", "simple-obfs", "obfs"}:
        if set(options) - {"obfs", "obfs-host"} or options.get("obfs") not in {"http", "tls"}:
            raise ValueError("Clash 无法完整转换此 Shadowsocks obfs 插件选项；请使用原始分享链接")
        return {
            "plugin": "obfs",
            "plugin-opts": {
                key: value
                for key, value in {
                    "mode": options.get("obfs"),
                    "host": options.get("obfs-host"),
                }.items()
                if value is not None
            },
        }
    if name == "v2ray-plugin":
        if (
            set(options) - {"mode", "host", "path", "tls", "mux"}
            or options.get("mode", "websocket") != "websocket"
        ):
            raise ValueError("Clash 无法完整转换此 v2ray-plugin 选项；请使用原始分享链接")
        return {
            "plugin": name,
            "plugin-opts": {
                key: value
                for key, value in {
                    "mode": options.get("mode", "websocket"),
                    "host": options.get("host"),
                    "path": options.get("path"),
                    "tls": str(options.get("tls", False)).lower() in {"true", "1"},
                    "mux": str(options.get("mux", False)).lower() in {"true", "1"},
                }.items()
                if value is not None
            },
        }
    raise ValueError(f"Clash 无法转换 Shadowsocks 插件 {name}；请使用原始分享链接")


def clash_compatibility_issues(
    protocol: str, network: str | None, extra: dict[str, Any], security: str | None = None
) -> list[str]:
    """Do not silently produce a different handshake for unsupported options.

    The target is standard Mihomo 1.19.31/1.19.32, not Xray or a Mihomo fork.
    Checks name only parameter keys, never credentials or mask packet contents.
    """
    issues: list[str] = []
    if security not in {None, "", "none", "tls", "reality"}:
        issues.append(f"Clash 尚未转换安全层 {security}；请使用原始分享链接")
    fm = extra.get("finalmask") or {}
    if fm:
        issues.append(
            "包含 fm / FinalMask，标准 Mihomo 1.19.31/1.19.32 不支持；"
            "请使用 Xray 客户端，或在服务端关闭 FinalMask 后重新导入链接"
        )
    transports = {
        "vless": {
            None,
            "tcp",
            "raw",
            "ws",
            "websocket",
            "grpc",
            "httpupgrade",
            "http",
            "h2",
            "xhttp",
        },
        "vmess": {None, "tcp", "raw", "ws", "websocket", "grpc", "httpupgrade", "http", "h2"},
        "trojan": {None, "tcp", "raw", "ws", "websocket", "grpc", "httpupgrade"},
    }
    if protocol in transports and network not in transports[protocol]:
        issues.append(f"标准 Mihomo 尚不能转换 {protocol} 的 {network} 传输；请使用原始分享链接")
    pins = extra.get("certificate_pins") or []
    if extra.get("header_type") not in {None, "", "none", "http"}:
        issues.append("Clash 尚未转换此传输的 headerType；请使用原始分享链接")
    if protocol == "trojan" and extra.get("header_type") == "http":
        issues.append("标准 Mihomo 不支持 Trojan 的 TCP HTTP 头伪装")
    if extra.get("vmess_fields"):
        issues.append("VMess 含尚未转换的扩展字段；已保留在分享链接和 JSON 备份中")
    if len(pins) > 1:
        issues.append("Clash 的 fingerprint 只能设置一个证书指纹，无法转换多个证书 pin")
    unknown = sorted(set(extra.get("share_params") or {}) - {"remarks", "remark", "group"})
    if unknown:
        issues.append(f"Clash 尚未转换参数 {', '.join(unknown)}；已保留在分享链接和 JSON 备份中")
    if protocol in {"ss", "ss2022"}:
        query = parse_qs(extra.get("plugin_query") or "")
        if set(query) - {"plugin", "group", "remarks"}:
            issues.append("Shadowsocks 含尚未转换的查询参数；已保留在分享链接和 JSON 备份中")
        try:
            ss_plugin_options(extra)
        except ValueError as exc:
            issues.append(str(exc))
    return issues


def share_extra_params(extra: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = dict(extra.get("share_params") or {})
    if extra.get("finalmask") is not None:
        params["fm"] = json.dumps(extra["finalmask"], ensure_ascii=False, separators=(",", ":"))
    return params
