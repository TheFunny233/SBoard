import base64
import json
import os
import shutil
import subprocess
from urllib.parse import urlencode

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from sboard.models import Node
from sboard.schemas import NodeCreate
from sboard.services.importer import parse_share_link
from sboard.services.subscriptions import _clash_proxy
from sboard.services.xhttp import clash_xhttp_options

UUID = "11111111-1111-1111-1111-111111111111"
PUBLIC_KEY = "SYB2tzJR0OfHxHLHsOTR9mQVdq61IgxyhDBDgCS6DBE"
DOWNLOAD = {
    "address": "192.0.2.2",
    "port": 28443,
    "network": "xhttp",
    "security": "reality",
    "realitySettings": {
        "serverName": "download.example.com",
        "fingerprint": "firefox",
        "publicKey": PUBLIC_KEY,
        "shortId": "9876543210abcdef",
    },
    "xhttpSettings": {"path": "/v1/responses", "mode": "auto"},
}


def xhttp_link(settings=None, *, mode="auto", path="/v1/responses") -> str:  # type: ignore[no-untyped-def]
    query = {
        "encryption": "none",
        "security": "reality",
        "sni": "upload.example.com",
        "fp": "chrome",
        "pbk": PUBLIC_KEY,
        "sid": "0123456789abcdef",
        "type": "xhttp",
        "host": "upload.example.com",
        "path": path,
        "mode": mode,
        "extra": json.dumps(settings if settings is not None else {"downloadSettings": DOWNLOAD}),
    }
    return f"vless://{UUID}@192.0.2.1:12811?{urlencode(query)}#Split"


def obfuscated_tls_settings():  # type: ignore[no-untyped-def]
    padding = {
        "xPaddingBytes": "24-80",
        "xPaddingObfsMode": True,
        "xPaddingHeader": "X-Request-ID",
        "xPaddingPlacement": "header",
        "xPaddingMethod": "tokenish",
        "sessionIDPlacement": "header",
        "sessionIDKey": "X-Correlation-ID",
        "seqPlacement": "query",
        "seqKey": "part",
    }
    return {
        **padding,
        "sessionIDTable": "Base62",
        "sessionIDLength": "18-30",
        "downloadSettings": {
            "address": "cdn.example.com",
            "port": 443,
            "network": "xhttp",
            "security": "tls",
            "tlsSettings": {
                "serverName": "cdn.example.com",
                "allowInsecure": False,
                "fingerprint": "chrome",
                "alpn": ["h2"],
            },
            "xhttpSettings": {
                "host": "cdn.example.com",
                "path": "/v1/responses/stream",
                "mode": "auto",
                "extra": padding,
            },
        },
    }


def test_obfuscated_reality_uplink_tls_download_roundtrip(client, admin_headers):
    settings = obfuscated_tls_settings()
    link = xhttp_link(settings, mode="stream-up", path="/v1/responses/stream")
    imported = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [link]},
    )
    assert imported.json()["created"] == 1
    token = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "TLS-download"},
    ).json()["token"]
    proxy = yaml.safe_load(client.get(f"/subscribe/clash/{token}").text)["proxies"][0]
    assert proxy["reality-opts"]["public-key"] == PUBLIC_KEY
    opts = proxy["xhttp-opts"]
    assert opts["mode"] == "stream-up"
    assert opts["x-padding-bytes"] == "24-80"
    assert opts["x-padding-obfs-mode"] is True
    assert opts["x-padding-header"] == "X-Request-ID"
    assert opts["x-padding-placement"] == "header"
    assert opts["x-padding-method"] == "tokenish"
    assert opts["session-placement"] == "header"
    assert opts["session-key"] == "X-Correlation-ID"
    assert opts["session-table"] == "Base62"
    assert opts["session-length"] == "18-30"
    assert opts["seq-placement"] == "query"
    assert opts["seq-key"] == "part"
    assert opts["download-settings"] == {
        "host": "cdn.example.com",
        "path": "/v1/responses/stream",
        "server": "cdn.example.com",
        "port": 443,
        "tls": True,
        "servername": "cdn.example.com",
        "alpn": ["h2"],
        "client-fingerprint": "chrome",
        "skip-cert-verify": False,
        "reality-opts": {"public-key": ""},
    }
    exported = client.get("/api/v1/nodes/export?format=links", headers=admin_headers).text
    assert parse_share_link(exported) == parse_share_link(link)


@pytest.mark.parametrize("security", ["tls", "none", "reality"])
def test_explicit_download_security_does_not_apply_stale_other_settings(security):
    settings = obfuscated_tls_settings()
    settings["downloadSettings"].update(
        security=security,
        realitySettings=DOWNLOAD["realitySettings"],
    )
    down = clash_xhttp_options("/", "example.com", {"xhttp_extra": settings})["download-settings"]
    assert down["tls"] is (security != "none")
    if security == "reality":
        assert down["reality-opts"]["public-key"] == PUBLIC_KEY
        assert down["servername"] == "download.example.com"
        assert "alpn" not in down
    else:
        assert down["reality-opts"] == {"public-key": ""}


def test_nested_transport_extra_and_current_session_names():
    opts = clash_xhttp_options(
        "/",
        "example.com",
        {
            "xhttp_extra": {
                "sessionPlacement": "path",
                "sessionIDPlacement": "header",
                "downloadSettings": {
                    "xhttpSettings": {
                        "extra": {
                            "headers": {"X-Test": "download"},
                            "xmux": {"maxConcurrency": "4-8"},
                        }
                    }
                },
            }
        },
    )
    assert opts["session-placement"] == "header"
    assert opts["download-settings"] == {
        "headers": {"X-Test": "download"},
        "reuse-settings": {"max-concurrency": "4-8"},
    }


@pytest.mark.parametrize("security", ["tls", "none", "reality"])
def test_generated_xhttp_config_loads_in_mihomo(tmp_path, security):
    binary = os.environ.get("MIHOMO_BIN") or shutil.which("mihomo")
    if not binary:
        pytest.skip("Set MIHOMO_BIN to validate generated configs with the actual core")
    settings = obfuscated_tls_settings()
    settings["downloadSettings"].update(security=security)
    if security == "reality":
        settings["downloadSettings"]["realitySettings"] = DOWNLOAD["realitySettings"]
    payload = NodeCreate.model_validate(
        parse_share_link(xhttp_link(settings, mode="stream-up", path="/v1/responses/stream"))
    )
    proxy = _clash_proxy(
        Node(
            **payload.model_dump(exclude={"extra", "group_ids", "tag_ids"}),
            extra_json=payload.extra,
        ),
        "core-test",
    )
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"proxies": [proxy], "rules": ["MATCH,core-test"]}), encoding="utf-8"
    )
    result = subprocess.run(
        [binary, "-t", "-d", str(tmp_path), "-f", str(path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_xhttp_import_subscription_and_share_link_roundtrip(client, admin_headers):
    response = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [xhttp_link()]},
    )
    assert response.json()["created"] == 1
    parsed = response.json()["items"][0]["node"]
    assert parsed["extra"]["xhttp_mode"] == "auto"
    assert parsed["extra"]["xhttp_extra"] == {"downloadSettings": DOWNLOAD}
    assert parsed["flow"] is None
    token = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "split"},
    ).json()["token"]
    proxy = yaml.safe_load(client.get(f"/subscribe/clash/{token}").text)["proxies"][0]
    assert proxy["server"] == "192.0.2.1"
    assert proxy["port"] == 12811
    assert proxy["servername"] == "upload.example.com"
    assert proxy["reality-opts"]["support-x25519mlkem768"] is True
    assert "flow" not in proxy
    assert proxy["xhttp-opts"] == {
        "path": "/v1/responses",
        "host": "upload.example.com",
        "mode": "auto",
        "download-settings": {
            "server": "192.0.2.2",
            "port": 28443,
            "tls": True,
            "path": "/v1/responses",
            "servername": "download.example.com",
            "client-fingerprint": "firefox",
            "reality-opts": {
                "public-key": PUBLIC_KEY,
                "short-id": "9876543210abcdef",
                "support-x25519mlkem768": True,
            },
        },
    }
    link = base64.b64decode(client.get(f"/subscribe/v2ray/{token}").text).decode()
    assert parse_share_link(link) == parse_share_link(xhttp_link())


@pytest.mark.parametrize(
    "settings",
    [[], "invalid", {"downloadSettings": []}, {"downloadSettings": {"xhttpSettings": "invalid"}}],
)
def test_invalid_xhttp_extra_is_atomic(client, admin_headers, settings):
    good = f"vless://{UUID}@example.com:443#Good"
    response = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [good, xhttp_link(settings)]},
    )
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert response.json()["created"] == 0
    assert client.get("/api/v1/nodes/export", headers=admin_headers).json()["nodes"] == []


def test_xhttp_download_inheritance_and_xmux():
    opts = clash_xhttp_options(
        "/up",
        "up.example.com",
        {
            "xhttp_extra": {
                "noGRPCHeader": False,
                "xmux": {"maxConcurrency": "16-32", "hKeepAlivePeriod": 0},
                "downloadSettings": {"address": "down.example.com", "port": 443},
            }
        },
    )
    assert opts["no-grpc-header"] is False
    assert opts["reuse-settings"] == {"max-concurrency": "16-32", "h-keep-alive-period": 0}
    assert opts["download-settings"] == {"server": "down.example.com", "port": 443}


@pytest.mark.parametrize("enabled", [True, False])
def test_xhttp_mlkem_setting_applies_to_both_reality_connections(enabled):
    payload = NodeCreate.model_validate(parse_share_link(xhttp_link()))
    payload.extra["reality_support_x25519mlkem768"] = enabled
    node = Node(
        **payload.model_dump(exclude={"extra", "group_ids", "tag_ids"}),
        extra_json=payload.extra,
    )
    proxy = _clash_proxy(node, "split")
    assert proxy["reality-opts"]["support-x25519mlkem768"] is enabled
    assert (
        proxy["xhttp-opts"]["download-settings"]["reality-opts"]["support-x25519mlkem768"]
        is enabled
    )
    # Other transports retain their existing handshake defaults.
    node.network = "tcp"
    proxy = _clash_proxy(node, "tcp")
    assert "support-x25519mlkem768" not in proxy["reality-opts"]


def test_xhttp_tls_download_does_not_enable_reality_mlkem():
    opts = clash_xhttp_options(
        "/up",
        "up.example.com",
        {
            "xhttp_extra": {
                "downloadSettings": {
                    "address": "down.example.com",
                    "security": "tls",
                    "tlsSettings": {"serverName": "down.example.com"},
                }
            },
        },
    )
    assert opts["download-settings"]["tls"] is True
    assert opts["download-settings"]["reality-opts"] == {"public-key": ""}


def test_distinct_xhttp_downloads_are_not_skipped_as_duplicates(client, admin_headers):
    settings = {"downloadSettings": {**DOWNLOAD, "address": "192.0.2.3"}}
    links = [xhttp_link(), xhttp_link(settings)]
    imported = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": links},
    )
    assert imported.json()["created"] == 2
    repeated = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": links},
    )
    assert repeated.json()["created"] == 0
    assert all(item["status"] == "skipped" for item in repeated.json()["items"])
    backup = client.get("/api/v1/nodes/export", headers=admin_headers).json()
    ids = [item["node_id"] for item in imported.json()["items"]]
    client.request("DELETE", "/api/v1/nodes/batch", headers=admin_headers, json={"ids": ids})
    restored = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={"mode": "commit", "backup": backup},
    )
    assert restored.json()["created"] == 2


def test_export_and_restore_node_backup(client: TestClient, admin_headers):
    group = client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={
            "name": "迁移分组",
            "strategy": "url-test",
            "test_interval": 600,
            "test_tolerance": 100,
        },
    ).json()
    tag = client.post(
        "/api/v1/tags",
        headers=admin_headers,
        json={
            "name": "迁移标签",
            "color": "#123456",
        },
    ).json()
    node = parse_share_link(xhttp_link())
    node.update(enabled=False, sort_order=42, group_ids=[group["id"]], tag_ids=[tag["id"]])
    created = client.post("/api/v1/nodes", headers=admin_headers, json=node)
    assert created.status_code == 201
    exported = client.get("/api/v1/nodes/export", headers=admin_headers)
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["content-disposition"] == 'attachment; filename="sboard-nodes.json"'
    backup = exported.json()
    assert backup["nodes"] == [NodeCreate.model_validate(node).model_dump()]
    assert backup["groups"][0]["strategy"] == "url-test"
    assert backup["tags"][0]["color"] == "#123456"
    text = client.get("/api/v1/nodes/export?format=links", headers=admin_headers)
    assert parse_share_link(text.text)["extra"] == node["extra"]
    client.delete(f"/api/v1/nodes/{created.json()['id']}", headers=admin_headers)
    client.delete(f"/api/v1/groups/{group['id']}", headers=admin_headers)
    client.delete(f"/api/v1/tags/{tag['id']}", headers=admin_headers)
    preview = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={
            "backup": backup,
            "mode": "preview",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["status"] == "valid"
    assert client.get("/api/v1/nodes/export", headers=admin_headers).json()["nodes"] == []
    assert client.get("/api/v1/groups", headers=admin_headers).json() == []
    restored = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={
            "backup": backup,
            "mode": "commit",
        },
    )
    assert restored.status_code == 200
    assert restored.json()["created"] == 1
    after = client.get("/api/v1/nodes/export", headers=admin_headers).json()
    original = backup["nodes"][0]
    actual = after["nodes"][0]
    assert actual.pop("group_ids") == [after["groups"][0]["id"]]
    assert actual.pop("tag_ids") == [after["tags"][0]["id"]]
    assert actual == {
        key: value for key, value in original.items() if key not in {"group_ids", "tag_ids"}
    }
    assert after["groups"][0]["test_interval"] == 600
    # Repeated restore skips duplicates; existing destination policy stays intact.
    client.patch(
        f"/api/v1/groups/{after['groups'][0]['id']}",
        headers=admin_headers,
        json={"strategy": "fallback"},
    )
    repeated = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={
            "backup": backup,
            "mode": "commit",
        },
    )
    assert repeated.json()["created"] == 0
    assert repeated.json()["items"][0]["status"] == "skipped"
    assert client.get("/api/v1/groups", headers=admin_headers).json()[0]["strategy"] == "fallback"


def test_export_all_has_no_page_or_enabled_limit(client, admin_headers):
    # Seed directly to avoid per-node TCP status probes in the create API.
    from sboard import database

    with Session(database.engine) as db:
        for index in range(505):
            db.add(
                Node(
                    **{
                        **NodeCreate.model_validate(parse_share_link(xhttp_link())).model_dump(
                            exclude={"group_ids", "tag_ids", "extra"}
                        ),
                        "name": f"node-{index}",
                        "enabled": index % 2 == 0,
                    },
                    extra_json={},
                )
            )
        db.commit()
    backup = client.get("/api/v1/nodes/export", headers=admin_headers).json()
    assert len(backup["nodes"]) == 505
    assert any(not node["enabled"] for node in backup["nodes"])
    links = client.get("/api/v1/nodes/export?format=links", headers=admin_headers).text.splitlines()
    assert len(links) == 505
    preview = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "preview", "links": links},
    )
    assert preview.status_code == 200
    assert preview.json()["total"] == 505
    assert preview.json()["failed"] == 0
    # A backup must restore all records, even when connection parameters repeat.
    with Session(database.engine) as db:
        db.execute(delete(Node))
        db.commit()
    restored = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={"mode": "commit", "backup": backup},
    )
    assert restored.status_code == 200
    assert restored.json()["created"] == 505


def test_backup_authentication_and_validation(client, admin_headers):
    assert client.get("/api/v1/nodes/export").status_code == 401
    assert client.post("/api/v1/nodes/import-backup", json={}).status_code == 401
    invalid = {"format": "sboard-nodes", "version": 2, "nodes": []}
    assert (
        client.post(
            "/api/v1/nodes/import-backup",
            headers=admin_headers,
            json={"backup": invalid, "mode": "commit"},
        ).status_code
        == 422
    )
    missing_group = parse_share_link(xhttp_link())
    missing_group["group_ids"] = ["missing"]
    invalid.update(version=1, nodes=[missing_group])
    assert (
        client.post(
            "/api/v1/nodes/import-backup",
            headers=admin_headers,
            json={"backup": invalid, "mode": "commit"},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/nodes/export", headers=admin_headers).json()["nodes"] == []


def test_backup_wireguard_and_managed_nodes(client, admin_headers):
    backup = {
        "format": "sboard-nodes",
        "version": 1,
        "nodes": [
            {
                "source_type": "managed",
                "agent_id": "old-agent",
                "name": "managed",
                "address": "example.com",
                "port": 443,
                "protocol": "vless",
                "uuid": UUID,
            },
            {
                "source_type": "external",
                "name": "wg",
                "address": "example.com",
                "port": 51820,
                "protocol": "wireguard",
                "extra": {"private_key": "example"},
            },
        ],
    }
    restored = client.post(
        "/api/v1/nodes/import-backup",
        headers=admin_headers,
        json={"backup": backup, "mode": "commit"},
    )
    assert restored.json()["created"] == 2
    assert restored.json()["items"][0]["warning"]
    nodes = client.get("/api/v1/nodes/export", headers=admin_headers).json()["nodes"]
    assert all(node["source_type"] == "external" and node["agent_id"] is None for node in nodes)
    text = client.get("/api/v1/nodes/export?format=links", headers=admin_headers)
    assert text.status_code == 422
    assert "JSON" in text.json()["detail"]["message"]
