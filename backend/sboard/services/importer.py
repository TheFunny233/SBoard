from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from sboard.services.link_options import certificate_pin, validate_finalmask
from sboard.services.xhttp import validate_xhttp_extra


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
        "tls": False,
        "reality": False,
        "group_ids": [],
        "tag_ids": [],
    }


def _common_extra(query: dict[str, list[str]], protocol: str = "vless") -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, names in {
        "client_fingerprint": ("fp", "fingerprint"),
        "spider_x": ("spx", "spider-x", "spiderX"),
        "header_type": ("headerType", "header-type"),
        "ech": ("ech",),
        "verify_cert_name": ("vcn",),
    }.items():
        if value := _first(query, *names):
            extra[key] = value
    if value := _first(query, "allowInsecure", "insecure", "allow_insecure"):
        extra["allow_insecure"] = value.lower() in {"1", "true"}
    if query.get("alpn"):
        extra["alpn"] = [part for value in query["alpn"] for part in value.split(",") if part]
    if value := _first(query, "pinSHA256", "pcs"):
        extra["certificate_pins"] = [certificate_pin(pin) for pin in value.split(",")]
    if value := _first(query, "fm"):
        try:
            fm = json.loads(value)
        except ValueError as exc:
            raise ImportParseError("invalid fm / FinalMask JSON") from exc
        validate_finalmask(fm)
        extra["finalmask"] = fm
    # Future/Xray-only parameters must survive export even if Mihomo cannot use them.
    known = {
        "security",
        "sni",
        "serverName",
        "peer",
        "pbk",
        "publicKey",
        "sid",
        "shortId",
        "flow",
        "type",
        "network",
        "path",
        "host",
        "serviceName",
        "encryption",
        "fp",
        "fingerprint",
        "spx",
        "spider-x",
        "spiderX",
        "headerType",
        "header-type",
        "allowInsecure",
        "insecure",
        "allow_insecure",
        "alpn",
        "ech",
        "vcn",
        "pcs",
        "pinSHA256",
        "fm",
        "mode",
        "extra",
        "obfs",
        "obfs-password",
        "obfsPassword",
        "mport",
        "ports",
        "hopInterval",
        "hop-interval",
        "up",
        "down",
        "minPacketSize",
        "maxPacketSize",
        "congestion_control",
        "congestion-controller",
        "udp_relay_mode",
        "udp-relay-mode",
        "disable_sni",
        "reduce_rtt",
    }
    # A field acknowledged for another protocol must not disappear on this one.
    if protocol != "hysteria2":
        known -= {
            "obfs",
            "obfs-password",
            "obfsPassword",
            "mport",
            "ports",
            "hopInterval",
            "hop-interval",
            "up",
            "down",
            "minPacketSize",
            "maxPacketSize",
        }
    if protocol != "tuic":
        known -= {
            "congestion_control",
            "congestion-controller",
            "udp_relay_mode",
            "udp-relay-mode",
            "disable_sni",
            "reduce_rtt",
        }
    if (_first(query, "type", "network") or "tcp") != "xhttp":
        known -= {"mode", "extra"}
    unknown = {key: values for key, values in query.items() if key not in known}
    if unknown:
        extra["share_params"] = unknown
    return extra


def _parse_standard_uri(
    link: str, protocol: str, *, default_security: str = "", default_port: int | None = None
) -> dict[str, Any]:
    parsed = urlsplit(link)
    port = parsed.port if parsed.port is not None else default_port
    if not parsed.hostname or port is None:
        raise ImportParseError("link must contain host and port")
    query = parse_qs(parsed.query, keep_blank_values=True)
    node = _base_node(
        protocol,
        parsed.hostname,
        port,
        _name(parsed.fragment, protocol, parsed.hostname, port),
    )
    security = (_first(query, "security") or default_security).lower()
    node.update(
        {
            "uuid": unquote(parsed.username or "") or None,
            "tls": security in {"tls", "reality"},
            "reality": security == "reality",
            "sni": _first(query, "sni", "serverName", "peer"),
            "public_key": _first(query, "pbk", "publicKey"),
            "short_id": _first(query, "sid", "shortId"),
            # Flow changes the VLESS handshake and must be copied exactly from
            # the source link.  Reality does not imply Vision.
            "flow": _first(query, "flow"),
            "network": _first(query, "type", "network") or "tcp",
            "security": security or None,
            "path": _first(query, "path"),
            "host": _first(query, "host"),
            "service_name": _first(query, "serviceName"),
            "extra": _common_extra(query, protocol),
        }
    )
    node["extra"] = {key: value for key, value in node["extra"].items() if value}
    encryption = _first(query, "encryption")
    if encryption and encryption != "none":
        node["extra"]["encryption"] = encryption
    if node["network"] == "xhttp":
        mode = _first(query, "mode")
        if mode:
            node["extra"]["xhttp_mode"] = mode
        raw_extra = _first(query, "extra")
        if raw_extra:
            try:
                settings = json.loads(raw_extra)
            except (ValueError, TypeError) as exc:
                raise ImportParseError("invalid XHTTP extra JSON") from exc
            try:
                validate_xhttp_extra(settings)
            except ValueError as exc:
                raise ImportParseError(str(exc)) from exc
            node["extra"]["xhttp_extra"] = settings
    return node


def _parse_password_uri(link: str, protocol: str) -> dict[str, Any]:
    parsed = urlsplit(link)
    node = _parse_standard_uri(link, protocol, default_security="tls", default_port=443)
    node.pop("uuid", None)
    # Hysteria's userpass auth is the complete userinfo, including the colon.
    node["password"] = unquote(parsed.netloc.rsplit("@", 1)[0]) if "@" in parsed.netloc else None
    return node


def _parse_hysteria2(link: str) -> dict[str, Any]:
    parsed = urlsplit(link)
    # urllib's .port only accepts one integer; Hysteria allows port ranges here.
    authority = parsed.netloc.rsplit("@", 1)[-1]
    raw_port = (
        authority.rsplit(":", 1)[-1] if not authority.endswith("]") and ":" in authority else ""
    )
    ports = None
    if raw_port and not raw_port.isdigit():
        ports = raw_port
        first_port = _validate_ports(ports)
        endpoint = authority[: -len(raw_port)] + str(first_port)
        userinfo = parsed.netloc[: -len(authority)]
        link = parsed._replace(netloc=userinfo + endpoint).geturl()
    node = _parse_password_uri(link, "hysteria2")
    query = parse_qs(urlsplit(link).query, keep_blank_values=True)
    node["extra"].update(
        {
            "obfs": _first(query, "obfs"),
            "obfs_password": _first(query, "obfs-password", "obfsPassword"),
        }
    )
    ports = _first(query, "mport", "ports") or ports
    if ports:
        _validate_ports(ports)
        node["extra"]["ports"] = ports.replace(":", "-")
    for target, names in {
        "hop_interval": ("hopInterval", "hop-interval"),
        "up": ("up",),
        "down": ("down",),
        "obfs_min_packet_size": ("minPacketSize",),
        "obfs_max_packet_size": ("maxPacketSize",),
    }.items():
        if value := _first(query, *names):
            node["extra"][target] = int(value) if "packet_size" in target else value
    return node


def _validate_ports(value: str) -> int:
    for segment in value.split(","):
        if not re.fullmatch(r"\d+(?:[-:]\d+)?", segment):
            raise ImportParseError("invalid Hysteria2 port range")
        bounds = [int(item) for item in re.split("[-:]", segment)]
        if any(port < 1 or port > 65535 for port in bounds) or bounds != sorted(bounds):
            raise ImportParseError("invalid Hysteria2 port range")
    return int(re.split("[-:,]", value)[0])


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
                **_common_extra(query, "tuic"),
                "congestion_controller": _first(
                    query, "congestion_control", "congestion-controller"
                ),
                "udp_relay_mode": _first(query, "udp_relay_mode", "udp-relay-mode"),
                "allow_insecure": (_first(query, "allow_insecure", "allowInsecure") or "0").lower()
                in {"1", "true"},
            },
        }
    )
    for key in ("disable_sni", "reduce_rtt"):
        if value := _first(query, key):
            node["extra"][key] = value.lower() in {"1", "true"}
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
                **_common_extra(
                    {
                        key: [str(data[key])]
                        for key in ("fp", "alpn", "allowInsecure", "insecure", "ech", "pcs", "vcn")
                        if data.get(key) is not None
                    }
                ),
                "header_type": str(data.get("type") or "none"),
            },
        }
    )
    if data.get("fm"):
        fm = json.loads(data["fm"]) if isinstance(data["fm"], str) else data["fm"]
        validate_finalmask(fm)
        node["extra"]["finalmask"] = fm
    if node["network"] == "xhttp":
        settings = data.get("extra") or {}
        settings = json.loads(settings) if isinstance(settings, str) else settings
        validate_xhttp_extra(settings)
        node["extra"].update(xhttp_mode=data.get("mode") or "auto", xhttp_extra=settings)
    recognized = {
        "v",
        "ps",
        "add",
        "port",
        "id",
        "aid",
        "scy",
        "net",
        "type",
        "host",
        "path",
        "tls",
        "sni",
        "fp",
        "alpn",
        "allowInsecure",
        "insecure",
        "ech",
        "pcs",
        "vcn",
        "fm",
        "mode",
        "extra",
    }
    unknown = {key: value for key, value in data.items() if key not in recognized}
    if unknown:
        node["extra"]["vmess_fields"] = unknown
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
            credentials = unquote(credentials)
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
            "cipher": cipher,
            "password": password,
            "network": "tcp",
            "security": "none",
            "extra": {"plugin_query": query_string} if query_string else {},
        }
    )
    return node


def parse_share_link(link: str) -> dict[str, Any]:
    link = link.strip()
    scheme = link.partition("://")[0].lower()
    if "://" in link:
        link = scheme + "://" + link.partition("://")[2]
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
