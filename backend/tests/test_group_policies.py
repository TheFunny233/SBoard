import base64

import pytest
import yaml
from sqlalchemy import create_engine, inspect, text

from sboard import database
from sboard.services.subscriptions import GEOSITE_URL


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


def test_independent_groups_manual_rules_and_node_toggle(client, admin_headers):  # type: ignore[no-untyped-def]
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
    for name, group_id, conditions, order in [
        ("AI route", ai["id"], ["DOMAIN-SUFFIX,chatgpt.com", "GEOSITE,category-ai-!cn"], -200),
        ("Bulk route", bulk["id"], ["GEOSITE,category-porn", "GEOSITE,category-dev"], -100),
    ]:
        response = client.post(
            "/api/v1/rules",
            headers=admin_headers,
            json={
                "name": name,
                "target_mode": "group",
                "group_id": group_id,
                "rules": conditions,
                "sort_order": order,
            },
        )
        assert response.status_code == 201, response.text
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
    assert document["geox-url"]["geosite"] == GEOSITE_URL
    assert document["geo-auto-update"] is True
    assert document["geo-update-interval"] == 24
    assert document["rules"] == [
        "DOMAIN-SUFFIX,chatgpt.com,AI",
        "GEOSITE,category-ai-!cn,AI",
        "GEOSITE,category-porn,大流量",
        "GEOSITE,category-dev,大流量",
        "MATCH,Proxy",
    ]

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


def test_node_membership_in_default_clash_groups(client, admin_headers):  # type: ignore[no-untyped-def]
    ai = group(client, admin_headers, "AI", strategy="url-test")
    ai_node = node(client, admin_headers, "AI only", [ai["id"]])
    general_node = node(client, admin_headers, "General", [])
    result = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "AI route",
            "target_mode": "group",
            "group_id": ai["id"],
            "rules": ["DOMAIN-SUFFIX,chatgpt.com"],
        },
    )
    assert result.status_code == 201
    sub_result = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "Default groups", "config": {"group_name": "节点选择"}},
    ).json()
    url = f"/subscribe/clash/{sub_result['token']}"
    initial = client.get(url)
    initial_groups = yaml.safe_load(initial.text)["proxy-groups"]
    assert initial_groups[0]["proxies"] == ["Auto", "AI only", "General", "DIRECT"]
    assert initial_groups[1]["proxies"] == ["AI only", "General"]

    def update_membership(node_id, changes):  # type: ignore[no-untyped-def]
        response = client.patch(f"/api/v1/nodes/{node_id}", headers=admin_headers, json=changes)
        assert response.status_code == 200, response.text
        updated = response.json()
        assert all(updated[key] == value for key, value in changes.items())

    update_membership(ai_node["id"], {"include_in_main_group": False})
    update_membership(general_node["id"], {"include_in_auto_group": False})
    _, document = preview(client, admin_headers, sub_result["subscription"])
    assert {item["name"]: item["proxies"] for item in document["proxy-groups"]} == {
        "节点选择": ["Auto", "General", "DIRECT"],
        "Auto": ["AI only"],
        "AI": ["AI only"],
    }

    update_membership(ai_node["id"], {"include_in_auto_group": False})
    public = client.get(url, headers={"If-None-Match": initial.headers["etag"]})
    assert public.status_code == 200
    assert public.headers["etag"] != initial.headers["etag"]
    document = yaml.safe_load(public.text)
    assert {item["name"]: item["proxies"] for item in document["proxy-groups"]} == {
        "节点选择": ["General", "DIRECT"],
        "AI": ["AI only"],
    }
    assert [proxy["name"] for proxy in document["proxies"]] == ["AI only", "General"]


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


def test_plain_subscriptions_do_not_add_geodata_settings(client, admin_headers):  # type: ignore[no-untyped-def]
    sub = client.post(
        "/api/v1/subscriptions", headers=admin_headers, json={"name": "plain"}
    ).json()["subscription"]
    _, document = preview(client, admin_headers, sub)
    assert "geox-url" not in document
    assert "geo-auto-update" not in document
    client.patch(
        f"/api/v1/subscriptions/{sub['id']}",
        headers=admin_headers,
        json={"config": {"rules": ["GEOSITE,category-porn,REJECT"]}},
    )
    _, document = preview(client, admin_headers, sub)
    assert document["geox-url"]["geosite"] == GEOSITE_URL


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
        connection.execute(text("CREATE TABLE nodes (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO nodes (id) VALUES ('legacy-node')"))
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
        node_defaults = connection.execute(
            text("SELECT include_in_main_group, include_in_auto_group FROM nodes")
        ).one()
        assert node_defaults == (True, True)
    assert {column["name"] for column in inspect(engine).get_columns("rule_sets")} >= {
        "template_key",
        "group_id",
    }
    engine.dispose()
