import base64

import pytest
import yaml
from sqlalchemy import create_engine, inspect, text

from sboard import database
from sboard.services.rule_templates import RULE_TEMPLATES


@pytest.fixture(autouse=True)
def no_tcp_probe(monkeypatch):  # type: ignore[no-untyped-def]
    def offline(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("test node")

    monkeypatch.setattr("sboard.services.state.socket.create_connection", offline)


def group(client, headers, name, **policy):  # type: ignore[no-untyped-def]
    response = client.post("/api/v1/groups", headers=headers, json={"name": name, **policy})
    assert response.status_code == 201, response.text
    return response.json()


def node(client, headers, name, group_ids):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/nodes",
        headers=headers,
        json={
            "name": name,
            "source_type": "external",
            "protocol": "vless",
            "address": "test.example.com",
            "port": 443,
            "uuid": "11111111-1111-1111-1111-111111111111",
            "group_ids": group_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, headers, subscription):  # type: ignore[no-untyped-def]
    response = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/preview?format=clash", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json(), yaml.safe_load(response.json()["content"])


def test_independent_groups_defaults_and_node_toggle(client, admin_headers):  # type: ignore[no-untyped-def]
    ai = group(
        client,
        admin_headers,
        "AI",
        strategy="url-test",
        test_interval=120,
        test_tolerance=80,
        test_url="https://example.com/204",
    )
    bulk = group(client, admin_headers, "大流量", strategy="fallback", test_interval=600)
    ai_node = node(client, admin_headers, "Clean", [ai["id"]])
    bulk_node = node(client, admin_headers, "Bulk", [bulk["id"]])
    disabled = node(client, admin_headers, "Disabled", [ai["id"], bulk["id"]])
    assert (
        client.patch(
            f"/api/v1/nodes/{disabled['id']}", headers=admin_headers, json={"enabled": False}
        ).status_code
        == 200
    )
    custom = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "My custom rule",
            "target_mode": "reject",
            "rules": ["DOMAIN,ads.example.com"],
        },
    ).json()
    payload = {"ai_group_id": ai["id"], "bulk_group_id": bulk["id"]}
    applied = client.post("/api/v1/rules/defaults", headers=admin_headers, json=payload)
    assert applied.status_code == 200, applied.text
    ids = {rule["id"] for rule in applied.json()}
    repeated = client.post("/api/v1/rules/defaults", headers=admin_headers, json=payload)
    assert {rule["id"] for rule in repeated.json()} == ids
    all_rules = client.get("/api/v1/rules", headers=admin_headers).json()
    assert len(all_rules) == len(RULE_TEMPLATES) + 1
    assert next(rule for rule in all_rules if rule["id"] == custom["id"]) == custom
    sub_result = client.post(
        "/api/v1/subscriptions", headers=admin_headers, json={"name": "all"}
    ).json()
    sub = sub_result["subscription"]
    result, document = preview(client, admin_headers, sub)
    policies = {item["name"]: item for item in document["proxy-groups"]}
    assert policies["AI"] == {
        "name": "AI",
        "type": "url-test",
        "proxies": ["Clean"],
        "url": "https://example.com/204",
        "interval": 120,
        "tolerance": 80,
        "lazy": False,
    }
    assert policies["大流量"] == {
        "name": "大流量",
        "type": "fallback",
        "proxies": ["Bulk"],
        "url": "https://www.gstatic.com/generate_204",
        "interval": 600,
        "lazy": False,
    }
    assert result["included_node_ids"] == [bulk_node["id"], ai_node["id"]]
    for domain in ["chatgpt.com", "sora.com", "grok.com", "perplexity.ai", "oaistatic.com"]:
        assert f"DOMAIN-SUFFIX,{domain},AI" in document["rules"]
    for domain in [
        "missav.ws",
        "hanimeone.me",
        "jsdelivr.net",
        "cdnjs.cloudflare.com",
        "cloudflaremirrors.com",
        "kali.download",
        "npmjs.org",
        "unpkg.com",
    ]:
        assert f"DOMAIN-SUFFIX,{domain},大流量" in document["rules"]
    rules = document["rules"]
    assert rules.index("DOMAIN,gemini.google.com,AI") < rules.index(
        "DOMAIN-SUFFIX,google.com,大流量"
    )
    assert rules.index("DOMAIN-SUFFIX,jsdelivr.net,大流量") < rules.index(
        "GEOIP,CN,DIRECT,no-resolve"
    )
    assert rules[-1] == "MATCH,Proxy"

    # Toggling affects public exports, ETags and every group, then restores membership.
    url = f"/subscribe/clash/{sub_result['token']}"
    original = client.get(url)
    client.patch(f"/api/v1/nodes/{ai_node['id']}", headers=admin_headers, json={"enabled": False})
    changed = client.get(url, headers={"If-None-Match": original.headers["etag"]})
    assert changed.status_code == 200
    assert changed.headers["etag"] != original.headers["etag"]
    result, document = preview(client, admin_headers, sub)
    assert result["included_node_ids"] == [bulk_node["id"]]
    assert all(item["name"] != "AI" for item in document["proxy-groups"])
    assert any("has no nodes" in warning for warning in result["warnings"])
    links = client.get(f"/subscribe/v2ray/{sub_result['token']}").text
    assert "Clean" not in base64.b64decode(links).decode()
    restored = client.patch(
        f"/api/v1/nodes/{ai_node['id']}", headers=admin_headers, json={"enabled": True}
    ).json()
    assert restored["group_ids"] == [ai["id"]]
    _, document = preview(client, admin_headers, sub)
    assert next(p for p in document["proxy-groups"] if p["name"] == "AI")["proxies"] == ["Clean"]


@pytest.mark.parametrize(
    "changes",
    [
        {"strategy": "invalid"},
        {"strategy": None},
        {"test_url": "file:///etc/passwd"},
        {"test_url": "https://user:pass@example.com"},
        {"test_url": None},
        {"test_interval": 29},
        {"test_interval": 86401},
        {"test_interval": None},
        {"test_tolerance": -1},
        {"test_tolerance": 1001},
        {"test_tolerance": None},
    ],
)
def test_group_policy_validation(client, admin_headers, changes):  # type: ignore[no-untyped-def]
    created = group(client, admin_headers, "Validate")
    response = client.patch(f"/api/v1/groups/{created['id']}", headers=admin_headers, json=changes)
    assert response.status_code == 422
    assert client.get("/api/v1/groups", headers=admin_headers).json()[0] == created


def test_defaults_invalid_target_does_not_modify_rules(client, admin_headers):  # type: ignore[no-untyped-def]
    created = group(client, admin_headers, "AI")
    response = client.post(
        "/api/v1/rules/defaults",
        headers=admin_headers,
        json={"ai_group_id": created["id"], "bulk_group_id": "missing"},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/rules", headers=admin_headers).json() == []
    assert client.post("/api/v1/rules/defaults", json={}).status_code == 401


def test_defaults_adopt_legacy_templates(client, admin_headers):  # type: ignore[no-untyped-def]
    created = group(client, admin_headers, "Migrated")
    legacy = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "大流量与开发站点",
            "target_mode": "direct",
            "rules": ["DOMAIN,old.example.com"],
        },
    ).json()
    applied = client.post(
        "/api/v1/rules/defaults",
        headers=admin_headers,
        json={"ai_group_id": created["id"], "bulk_group_id": created["id"]},
    ).json()
    upgraded = next(rule for rule in applied if rule["id"] == legacy["id"])
    assert upgraded["target_mode"] == "group"
    assert upgraded["group_id"] == created["id"]


def test_group_name_collisions_and_subscription_filter(client, admin_headers):  # type: ignore[no-untyped-def]
    created = group(client, admin_headers, "Proxy", strategy="url-test")
    first = node(client, admin_headers, "Proxy", [created["id"]])
    node(client, admin_headers, "Proxy (2)", [created["id"]])
    client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "Route",
            "target_mode": "group",
            "group_id": created["id"],
            "rules": ["DOMAIN,test.example.com"],
        },
    )
    sub = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={
            "name": "limited",
            "include_all_nodes": False,
            "node_ids": [first["id"]],
        },
    ).json()["subscription"]
    _, document = preview(client, admin_headers, sub)
    names = [item["name"] for item in document["proxies"] + document["proxy-groups"]]
    assert len(names) == len(set(names))
    route = document["proxy-groups"][-1]
    assert route["proxies"] == ["Proxy (2)"]
    assert document["rules"][0] == f"DOMAIN,test.example.com,{route['name']}"
    updated = client.patch(
        f"/api/v1/groups/{created['id']}", headers=admin_headers, json={"strategy": "select"}
    )
    assert updated.status_code == 200
    _, document = preview(client, admin_headers, sub)
    assert document["proxy-groups"][-1] == {
        "name": route["name"],
        "type": "select",
        "proxies": ["Proxy (2)"],
    }


def test_existing_sqlite_database_migrates_idempotently(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE groups (id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(100), description TEXT, sort_order INTEGER, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO groups VALUES "
                "('existing', 'AI', NULL, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(text("CREATE TABLE rule_sets (id VARCHAR(36) PRIMARY KEY)"))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()
    with engine.connect() as connection:
        row = (
            connection.execute(text("SELECT * FROM groups WHERE id = 'existing'")).mappings().one()
        )
        assert row["strategy"] == "select"
        assert row["test_interval"] == 300
        assert row["test_tolerance"] == 50
        assert row["test_url"] == "https://www.gstatic.com/generate_204"
    assert {column["name"] for column in inspect(engine).get_columns("rule_sets")} >= {
        "template_key",
        "group_id",
    }
    engine.dispose()
