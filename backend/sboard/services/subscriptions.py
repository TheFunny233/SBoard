from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sboard.models import Node, RuleSet, Subscription


@dataclass(slots=True)
class GeneratedSubscription:
    content: str
    node_ids: list[str]
    warnings: list[str]

    @property
    def etag(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def selected_nodes(db: Session, subscription: Subscription) -> list[Node]:
    if subscription.include_all_nodes:
        return list(
            db.scalars(
                select(Node)
                .where(Node.enabled.is_(True))
                .order_by(Node.sort_order, Node.name, Node.id)
            ).all()
        )

    by_id: dict[str, Node] = {}
    for node in subscription.nodes:
        by_id[node.id] = node
    for group in subscription.groups:
        for node in group.nodes:
            by_id[node.id] = node
    for tag in subscription.tags:
        for node in tag.nodes:
            by_id[node.id] = node
    return sorted(
        (node for node in by_id.values() if node.enabled),
        key=lambda node: (node.sort_order, node.name, node.id),
    )


def _unique_names(nodes: list[Node]) -> dict[str, str]:
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for node in nodes:
        base = node.name.strip() or f"{node.protocol}-{node.address}:{node.port}"
        counts[base] = counts.get(base, 0) + 1
        names[node.id] = base if counts[base] == 1 else f"{base} ({counts[base]})"
    return names


def _compact(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def _apply_transport(proxy: dict[str, Any], node: Node) -> None:
    if node.network in {None, "tcp"}:
        return
    proxy["network"] = node.network
    if node.network == "ws":
        ws: dict[str, Any] = {}
        if node.path:
            ws["path"] = node.path
        if node.host:
            ws["headers"] = {"Host": node.host}
        if ws:
            proxy["ws-opts"] = ws
    elif node.network == "grpc" and node.service_name:
        proxy["grpc-opts"] = {"grpc-service-name": node.service_name}
    elif node.network == "httpupgrade":
        opts: dict[str, Any] = {}
        if node.path:
            opts["path"] = node.path
        if node.host:
            opts["host"] = node.host
        if opts:
            proxy["http-upgrade-opts"] = opts


def _clash_proxy(node: Node, name: str) -> dict[str, Any] | None:
    extra = node.extra_json or {}
    common = {"name": name, "server": node.address, "port": node.port}

    if node.protocol == "vless":
        proxy = _compact(
            {
                **common,
                "type": "vless",
                "uuid": node.uuid,
                "udp": True,
                "tls": node.tls,
                "servername": node.sni,
                "flow": node.flow,
                "client-fingerprint": extra.get("client_fingerprint", "chrome")
                if node.reality
                else extra.get("client_fingerprint"),
            }
        )
        if node.reality:
            proxy["reality-opts"] = _compact(
                {"public-key": node.public_key, "short-id": node.short_id}
            )
        _apply_transport(proxy, node)
        return proxy

    if node.protocol == "vmess":
        proxy = _compact(
            {
                **common,
                "type": "vmess",
                "uuid": node.uuid,
                "alterId": int(extra.get("alter_id", 0)),
                "cipher": extra.get("cipher", "auto"),
                "udp": True,
                "tls": node.tls,
                "servername": node.sni,
            }
        )
        _apply_transport(proxy, node)
        return proxy

    if node.protocol == "trojan":
        proxy = _compact(
            {
                **common,
                "type": "trojan",
                "password": node.password,
                "udp": True,
                "sni": node.sni,
                "skip-cert-verify": bool(extra.get("allow_insecure", False)),
            }
        )
        _apply_transport(proxy, node)
        return proxy

    if node.protocol in {"ss", "ss2022"}:
        return _compact(
            {
                **common,
                "type": "ss",
                "cipher": node.cipher,
                "password": node.password,
                "udp": True,
            }
        )

    if node.protocol == "hysteria2":
        return _compact(
            {
                **common,
                "type": "hysteria2",
                "password": node.password,
                "sni": node.sni,
                "skip-cert-verify": bool(extra.get("allow_insecure", False)),
                "obfs": extra.get("obfs"),
                "obfs-password": extra.get("obfs_password"),
            }
        )

    if node.protocol == "tuic":
        return _compact(
            {
                **common,
                "type": "tuic",
                "uuid": node.uuid,
                "password": node.password,
                "sni": node.sni,
                "udp-relay-mode": extra.get("udp_relay_mode", "native"),
                "congestion-controller": extra.get("congestion_controller", "bbr"),
                "skip-cert-verify": bool(extra.get("allow_insecure", False)),
            }
        )
    return None


def _rule_with_target(condition: str, target: str) -> str:
    parts = [part.strip() for part in condition.split(",")]
    if parts[-1].lower() == "no-resolve":
        return ",".join([*parts[:-1], target, parts[-1]])
    return ",".join([*parts, target])


def _managed_rules(
    db: Session,
    included_node_ids: set[str],
    names: dict[str, str],
) -> tuple[list[str], list[str]]:
    rule_sets = db.scalars(
        select(RuleSet)
        .options(selectinload(RuleSet.target_node))
        .where(RuleSet.enabled.is_(True))
        .order_by(RuleSet.sort_order, RuleSet.name, RuleSet.id)
    ).all()
    rules: list[str] = []
    warnings: list[str] = []
    for rule_set in rule_sets:
        if rule_set.target_mode == "direct":
            target = "DIRECT"
        elif rule_set.target_mode == "reject":
            target = "REJECT"
        elif rule_set.node_id and rule_set.node_id in included_node_ids:
            target = names[rule_set.node_id]
        else:
            warnings.append(
                f"Rule set {rule_set.name} skipped because its target node is not in this subscription"
            )
            continue
        rules.extend(_rule_with_target(condition, target) for condition in rule_set.rules_json or [])
    return rules, warnings


def generate_clash(db: Session, subscription: Subscription) -> GeneratedSubscription:
    nodes = selected_nodes(db, subscription)
    names = _unique_names(nodes)
    proxies: list[dict[str, Any]] = []
    included: list[str] = []
    warnings: list[str] = []
    proxy_names: list[str] = []

    for node in nodes:
        proxy = _clash_proxy(node, names[node.id])
        if proxy is None:
            warnings.append(
                f"Node {node.name} ({node.id}) uses unsupported protocol {node.protocol}"
            )
            continue
        proxies.append(proxy)
        proxy_names.append(names[node.id])
        included.append(node.id)

    config = subscription.config_json or {}
    group_name = str(config.get("group_name") or "Proxy")
    auto_group_name = str(config.get("auto_group_name") or "Auto")
    test_url = str(config.get("test_url") or "https://www.gstatic.com/generate_204")
    interval = int(config.get("test_interval") or 300)
    include_auto = bool(config.get("include_auto", True))

    proxy_groups: list[dict[str, Any]] = []
    if proxy_names:
        choices = ([auto_group_name] if include_auto else []) + proxy_names + ["DIRECT"]
        proxy_groups.append({"name": group_name, "type": "select", "proxies": choices})
        if include_auto:
            proxy_groups.append(
                {
                    "name": auto_group_name,
                    "type": "url-test",
                    "proxies": proxy_names,
                    "url": test_url,
                    "interval": interval,
                }
            )
    else:
        proxy_groups.append({"name": group_name, "type": "select", "proxies": ["DIRECT"]})

    managed_rules, rule_warnings = _managed_rules(db, set(included), names)
    warnings.extend(rule_warnings)
    raw_rules = config.get("rules")
    subscription_rules = raw_rules if isinstance(raw_rules, list) and raw_rules else []
    rules = [*managed_rules, *subscription_rules]
    if not any(rule.strip().upper().startswith("MATCH,") for rule in rules):
        rules.append(f"MATCH,{group_name}")
    document = {"proxies": proxies, "proxy-groups": proxy_groups, "rules": rules}
    content = yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=4096)
    return GeneratedSubscription(content=content, node_ids=included, warnings=warnings)


def _b64_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _endpoint_host(address: str) -> str:
    return f"[{address}]" if ":" in address and not address.startswith("[") else address


def _share_link(node: Node, name: str) -> str | None:
    host = _endpoint_host(node.address)
    fragment = quote(name, safe="")
    extra = node.extra_json or {}

    if node.protocol == "vless" and node.uuid:
        query = _compact(
            {
                "type": node.network or "tcp",
                "security": "reality" if node.reality else ("tls" if node.tls else "none"),
                "sni": node.sni,
                "pbk": node.public_key if node.reality else None,
                "sid": node.short_id if node.reality else None,
                "flow": node.flow,
                "path": node.path,
                "host": node.host,
                "serviceName": node.service_name,
            }
        )
        return (
            f"vless://{quote(node.uuid, safe='')}@{host}:{node.port}?{urlencode(query)}#{fragment}"
        )

    if node.protocol == "vmess" and node.uuid:
        payload = {
            "v": "2",
            "ps": name,
            "add": node.address,
            "port": str(node.port),
            "id": node.uuid,
            "aid": str(extra.get("alter_id", 0)),
            "scy": str(extra.get("cipher", "auto")),
            "net": node.network or "tcp",
            "type": "none",
            "host": node.host or "",
            "path": node.service_name if node.network == "grpc" else (node.path or ""),
            "tls": "tls" if node.tls else "",
            "sni": node.sni or "",
        }
        encoded = base64.b64encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return f"vmess://{encoded}"

    if node.protocol == "trojan" and node.password:
        query = _compact(
            {
                "security": "tls" if node.tls else "none",
                "sni": node.sni,
                "type": node.network or "tcp",
                "path": node.path,
                "host": node.host,
                "serviceName": node.service_name,
                "allowInsecure": "1" if extra.get("allow_insecure") else None,
            }
        )
        return f"trojan://{quote(node.password, safe='')}@{host}:{node.port}?{urlencode(query)}#{fragment}"

    if node.protocol in {"ss", "ss2022"} and node.cipher and node.password:
        credentials = _b64_url(f"{node.cipher}:{node.password}".encode())
        return f"ss://{credentials}@{host}:{node.port}#{fragment}"

    if node.protocol == "hysteria2" and node.password:
        query = _compact(
            {
                "sni": node.sni,
                "insecure": "1" if extra.get("allow_insecure") else None,
                "obfs": extra.get("obfs"),
                "obfs-password": extra.get("obfs_password"),
            }
        )
        return f"hysteria2://{quote(node.password, safe='')}@{host}:{node.port}?{urlencode(query)}#{fragment}"

    if node.protocol == "tuic" and node.uuid and node.password:
        query = _compact(
            {
                "sni": node.sni,
                "congestion_control": extra.get("congestion_controller"),
                "udp_relay_mode": extra.get("udp_relay_mode"),
                "allow_insecure": "1" if extra.get("allow_insecure") else None,
            }
        )
        return (
            f"tuic://{quote(node.uuid, safe='')}:{quote(node.password, safe='')}"
            f"@{host}:{node.port}?{urlencode(query)}#{fragment}"
        )
    return None


def generate_v2ray(db: Session, subscription: Subscription) -> GeneratedSubscription:
    nodes = selected_nodes(db, subscription)
    names = _unique_names(nodes)
    links: list[str] = []
    included: list[str] = []
    warnings: list[str] = []
    for node in nodes:
        link = _share_link(node, names[node.id])
        if link is None:
            warnings.append(f"Node {node.name} ({node.id}) cannot be serialized as a share link")
            continue
        links.append(link)
        included.append(node.id)
    plain = "\n".join(links)
    content = base64.b64encode(plain.encode("utf-8")).decode("ascii")
    return GeneratedSubscription(content=content, node_ids=included, warnings=warnings)
