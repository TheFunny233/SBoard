import base64

import yaml
from fastapi.testclient import TestClient


def test_import_and_generate_subscriptions(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    link = (
        "vless://11111111-1111-1111-1111-111111111111@example.com:443"
        "?security=reality&type=tcp&sni=example.com&pbk=public-key&sid=abcd"
        "&fp=firefox&spx=%2Frobots.txt"
        "#Tokyo"
    )
    preview = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "preview", "links": [link], "name_prefix": "SBoard"},
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["node"]["protocol"] == "vless"
    assert preview.json()["items"][0]["node"]["name"] == "SBoard - Tokyo"
    assert preview.json()["items"][0]["node"]["flow"] is None
    assert preview.json()["items"][0]["node"]["extra"] == {
        "client_fingerprint": "firefox",
        "spider_x": "/robots.txt",
    }

    imported = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "commit", "links": [link]},
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 1

    subscription_response = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "default", "include_all_nodes": True},
    )
    assert subscription_response.status_code == 201
    subscription = subscription_response.json()
    token = subscription["token"]
    listed = client.get("/api/v1/subscriptions", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["token"] == token

    clash = client.get(f"/subscribe/clash/{token}")
    assert clash.status_code == 200
    assert clash.headers["content-disposition"] == (
        "attachment; filename=default; filename*=UTF-8''default"
    )
    document = yaml.safe_load(clash.text)
    assert document["proxies"][0]["type"] == "vless"
    assert "flow" not in document["proxies"][0]
    assert document["proxies"][0]["reality-opts"]["public-key"] == "public-key"
    assert document["proxies"][0]["reality-opts"]["spider-x"] == "/robots.txt"
    assert document["proxy-groups"]
    assert document["rules"]

    v2ray = client.get(f"/subscribe/v2ray/{token}")
    assert v2ray.status_code == 200
    decoded = base64.b64decode(v2ray.text).decode()
    assert decoded.startswith("vless://")
    assert "example.com:443" in decoded
    assert "fp=firefox" in decoded
    assert "spx=%2Frobots.txt" in decoded

    renamed = client.patch(
        f"/api/v1/subscriptions/{subscription['subscription']['id']}",
        headers=admin_headers,
        json={"name": "个人设备"},
    )
    assert renamed.status_code == 200
    renamed_clash = client.get(f"/subscribe/clash/{token}")
    assert renamed_clash.headers["content-disposition"] == (
        "attachment; filename=sboard; filename*=UTF-8''%E4%B8%AA%E4%BA%BA%E8%AE%BE%E5%A4%87"
    )

    cached = client.get(
        f"/subscribe/clash/{token}", headers={"If-None-Match": clash.headers["etag"]}
    )
    assert cached.status_code == 304


def test_import_preserves_explicit_vless_flow(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    link = (
        "vless://11111111-1111-1111-1111-111111111111@example.com:443"
        "?security=reality&type=tcp&flow=xtls-rprx-vision&sni=example.com"
        "&pbk=public-key#Vision"
    )
    preview = client.post(
        "/api/v1/nodes/import",
        headers=admin_headers,
        json={"mode": "preview", "links": [link]},
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["node"]["flow"] == "xtls-rprx-vision"


def test_managed_node_uses_agent_status(client: TestClient, admin_headers: dict[str, str]) -> None:
    agent = client.post(
        "/api/v1/agents", headers=admin_headers, json={"name": "managed-host"}
    ).json()
    node = client.post(
        "/api/v1/nodes",
        headers=admin_headers,
        json={
            "source_type": "managed",
            "agent_id": agent["agent"]["id"],
            "name": "managed-vless",
            "address": "node.example.com",
            "port": 443,
            "protocol": "vless",
            "uuid": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert node.status_code == 201
    assert node.json()["online_status"] == "offline"

    blocked_delete = client.delete(f"/api/v1/agents/{agent['agent']['id']}", headers=admin_headers)
    assert blocked_delete.status_code == 409


def test_external_node_reports_tcp_reachability(
    client: TestClient, admin_headers: dict[str, str], monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        "sboard.services.state.socket.create_connection", lambda *_args, **_kwargs: _Connection()
    )
    created = client.post(
        "/api/v1/nodes",
        headers=admin_headers,
        json={
            "source_type": "external",
            "name": "reachable",
            "address": "node.example.com",
            "port": 443,
            "protocol": "vless",
            "uuid": "11111111-1111-1111-1111-111111111111",
        },
    )
    assert created.status_code == 201
    assert created.json()["online_status"] == "online"


def test_batch_delete_nodes(client: TestClient, admin_headers: dict[str, str]) -> None:
    node_ids = []
    for index in range(2):
        response = client.post(
            "/api/v1/nodes",
            headers=admin_headers,
            json={
                "source_type": "external",
                "name": f"node-{index}",
                "address": f"node-{index}.example.com",
                "port": 443,
                "protocol": "vless",
                "uuid": f"11111111-1111-1111-1111-11111111111{index}",
            },
        )
        assert response.status_code == 201
        node_ids.append(response.json()["id"])

    missing_id = "00000000-0000-0000-0000-000000000000"
    deleted = client.request(
        "DELETE",
        "/api/v1/nodes/batch",
        headers=admin_headers,
        json={"ids": [*node_ids, node_ids[0], missing_id]},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 2, "missing_ids": [missing_id]}

    remaining = client.get("/api/v1/nodes", headers=admin_headers)
    assert remaining.status_code == 200
    assert remaining.json() == {"items": [], "total": 0}
