from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit


class ImportParseError(ValueError):
    pass


def _decode_base64(value: str) -> bytes:
    value = value.strip()
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise ImportParseError("invalid base64 data") from exc


def _first(query: dict[str, list[str]], *names: str) -> str | None:
    for name in names:
        values = query.get(name)
        if values and values[0] != "":
            return values[0]
    return None


def _name(fragment: str, protocol: str, address: str, port: int) -> str:
    return unquote(fragment) if fragment else f"{protocol}-{address}:{port}"


def _base_node(protocol: str, address: str, port: int, name: str) -> dict[str, Any]:
    return {
        "source_type": "external",
        "agent_id": None,
        "name": name,
        "address": address,
        "port": port,
        "protocol": protocol,
        "enabled": True,
        "sort_order": 0,
        "extra": {},
        "group_ids": [],
        "tag_ids": [],
    }


def _parse_standard_uri(link: str, protocol: str) -> dict[str, Any]:
    parsed = urlsplit(link)
    if not parsed.hostname or parsed.port is None:
        raise ImportParseError("link must contain host and port")
    query = parse_qs(parsed.query, keep_blank_values=True)
    node = _base_node(
        protocol,
        parsed.hostname,
        parsed.port,
        _name(parsed.fragment, protocol, parsed.hostname, parsed.port),
    )
    security = (_first(query, "security") or "").lower()
    default_flow = "xtls-rprx-vision" if protocol == "vless" and security == "reality" else None
    node.update(
        {
            "uuid": unquote(parsed.username or "") or None,
            "tls": security in {"tls", "reality"},
            "reality": security == "reality",
            "sni": _first(query, "sni", "serverName"),
            "public_key": _first(query, "pbk", "publicKey"),
            "short_id": _first(query, "sid", "shortId"),
            "flow": _first(query, "flow") or default_flow,
            "network": _first(query, "type", "network") or "tcp",
            "security": security or None,
            "path": _first(query, "path"),
            "host": _first(query, "host"),
            "service_name": _first(query, "serviceName"),
            "extra": {
                "client_fingerprint": _first(query, "fp", "fingerprint"),
                "spider_x": _first(query, "spx", "spider-x", "spiderX"),
                "header_type": _first(query, "headerType", "header-type"),
            },
        }
    )
    node["extra"] = {key: value for key, value in node["extra"].items() if value}
    return node


def _parse_password_uri(link: str, protocol: str) -> dict[str, Any]:
    parsed = urlsplit(link)
    if not parsed.hostname or parsed.port is None:
        raise ImportParseError("link must contain host and port")
    query = parse_qs(parsed.query, keep_blank_values=True)
    node = _base_node(
        protocol,
        parsed.hostname,
        parsed.port,
        _name(parsed.fragment, protocol, parsed.hostname, parsed.port),
    )
    security = (_first(query, "security") or "tls").lower()
    node.update(
        {
            "password": unquote(parsed.username or "") or None,
            "tls": security != "none",
            "sni": _first(query, "sni", "peer"),
            "network": _first(query, "type", "network") or "tcp",
            "security": security,
            "path": _first(query, "path"),
            "host": _first(query, "host"),
            "service_name": _first(query, "serviceName"),
            "extra": {
                "allow_insecure": (_first(query, "allowInsecure", "insecure") or "0")
                in {"1", "true"}
            },
        }
    )
    return node


def _parse_hysteria2(link: str) -> dict[str, Any]:
    node = _parse_password_uri(link, "hysteria2")
    query = parse_qs(urlsplit(link).query, keep_blank_values=True)
    node["extra"].update(
        {
            "obfs": _first(query, "obfs"),
            "obfs_password": _first(query, "obfs-password", "obfsPassword"),
        }
    )
    return node


def _parse_tuic(link: str) -> dict[str, Any]:
    parsed = urlsplit(link)
    if not parsed.hostname or parsed.port is None:
        raise ImportParseError("link must contain host and port")
    query = parse_qs(parsed.query, keep_blank_values=True)
    node = _base_node(
        "tuic",
        parsed.hostname,
        parsed.port,
        _name(parsed.fragment, "tuic", parsed.hostname, parsed.port),
    )
    node.update(
        {
            "uuid": unquote(parsed.username or "") or None,
            "password": unquote(parsed.password or "") or None,
            "tls": True,
            "security": "tls",
            "sni": _first(query, "sni"),
            "extra": {
                "congestion_controller": _first(
                    query, "congestion_control", "congestion-controller"
                ),
                "udp_relay_mode": _first(query, "udp_relay_mode", "udp-relay-mode"),
                "allow_insecure": (_first(query, "allow_insecure", "allowInsecure") or "0")
                in {"1", "true"},
            },
        }
    )
    return node


def _parse_vmess(link: str) -> dict[str, Any]:
    raw = link.removeprefix("vmess://")
    try:
        data = json.loads(_decode_base64(raw).decode("utf-8"))
        address = str(data["add"])
        port = int(data["port"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImportParseError("invalid vmess link") from exc
    node = _base_node("vmess", address, port, str(data.get("ps") or f"vmess-{address}:{port}"))
    tls_value = str(data.get("tls") or "").lower()
    node.update(
        {
            "uuid": str(data.get("id") or "") or None,
            "tls": tls_value == "tls",
            "sni": str(data.get("sni") or "") or None,
            "network": str(data.get("net") or "tcp"),
            "security": "tls" if tls_value == "tls" else "none",
            "path": str(data.get("path") or "") or None,
            "host": str(data.get("host") or "") or None,
            "service_name": str(data.get("path") or "") or None
            if str(data.get("net") or "") == "grpc"
            else None,
            "extra": {
                "alter_id": int(data.get("aid") or 0),
                "cipher": str(data.get("scy") or "auto"),
            },
        }
    )
    return node


def _parse_ss(link: str) -> dict[str, Any]:
    raw = link.removeprefix("ss://")
    main, _, fragment = raw.partition("#")
    main, _, query_string = main.partition("?")
    name = unquote(fragment)

    if "@" in main:
        credentials, endpoint = main.rsplit("@", 1)
        if ":" not in credentials:
            credentials = _decode_base64(credentials).decode("utf-8")
    else:
        decoded = _decode_base64(main).decode("utf-8")
        if "@" not in decoded:
            raise ImportParseError("invalid shadowsocks link")
        credentials, endpoint = decoded.rsplit("@", 1)

    if ":" not in credentials:
        raise ImportParseError("invalid shadowsocks credentials")
    cipher, password = credentials.split(":", 1)
    endpoint_parsed = urlsplit(f"ss://unused@{endpoint}")
    if not endpoint_parsed.hostname or endpoint_parsed.port is None:
        raise ImportParseError("invalid shadowsocks endpoint")
    protocol = "ss2022" if cipher.startswith("2022-") else "ss"
    node = _base_node(
        protocol,
        endpoint_parsed.hostname,
        endpoint_parsed.port,
        name or f"{protocol}-{endpoint_parsed.hostname}:{endpoint_parsed.port}",
    )
    node.update(
        {
            "cipher": unquote(cipher),
            "password": unquote(password),
            "network": "tcp",
            "security": "none",
            "extra": {"plugin_query": query_string} if query_string else {},
        }
    )
    return node


def parse_share_link(link: str) -> dict[str, Any]:
    link = link.strip()
    scheme = link.partition("://")[0].lower()
    if scheme == "vless":
        return _parse_standard_uri(link, "vless")
    if scheme == "vmess":
        return _parse_vmess(link)
    if scheme == "trojan":
        return _parse_password_uri(link, "trojan")
    if scheme == "ss":
        return _parse_ss(link)
    if scheme in {"hysteria2", "hy2"}:
        return _parse_hysteria2(link)
    if scheme == "tuic":
        return _parse_tuic(link)
    raise ImportParseError(f"unsupported link scheme: {scheme or 'missing'}")
