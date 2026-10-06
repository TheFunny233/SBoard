import yaml
from fastapi.testclient import TestClient


def _create_node(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    suffix: int,
    group_ids: list[str] | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/nodes",
        headers=admin_headers,
        json={
            "source_type": "external",
            "name": name,
            "address": f"node-{suffix}.example.com",
            "port": 443,
            "protocol": "vless",
            "uuid": f"11111111-1111-1111-1111-11111111111{suffix}",
            "group_ids": group_ids or [],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_rule_crud_and_clash_generation(client: TestClient, admin_headers: dict[str, str]) -> None:
    target = _create_node(client, admin_headers, "AI node", 1)
    rule_response = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "OpenAI",
            "description": "AI traffic",
            "target_mode": "node",
            "node_id": target["id"],
            "rules": [
                "domain-suffix,openai.com",
                "DOMAIN-SUFFIX,chatgpt.com",
                "DOMAIN-SUFFIX,chatgpt.com",
            ],
            "sort_order": 10,
        },
    )
    assert rule_response.status_code == 201
    rule = rule_response.json()
    assert rule["target_node_name"] == "AI node"
    assert rule["rules"] == [
        "DOMAIN-SUFFIX,openai.com",
        "DOMAIN-SUFFIX,chatgpt.com",
    ]

    subscription = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "rules", "include_all_nodes": True},
    ).json()["subscription"]
    preview = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/preview?format=clash",
        headers=admin_headers,
    )
    assert preview.status_code == 200
    document = yaml.safe_load(preview.json()["content"])
    assert document["rules"] == [
        "DOMAIN-SUFFIX,openai.com,AI node",
        "DOMAIN-SUFFIX,chatgpt.com,AI node",
        "MATCH,Proxy",
    ]

    updated = client.patch(
        f"/api/v1/rules/{rule['id']}",
        headers=admin_headers,
        json={"target_mode": "direct", "node_id": None},
    )
    assert updated.status_code == 200
    assert updated.json()["target_mode"] == "direct"
    assert updated.json()["node_id"] is None

    deleted = client.delete(f"/api/v1/rules/{rule['id']}", headers=admin_headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/rules", headers=admin_headers).json() == []


def test_rule_target_outside_subscription_is_skipped(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    target = _create_node(client, admin_headers, "Target", 2)
    included = _create_node(client, admin_headers, "Included", 3)
    created = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "YouTube",
            "target_mode": "node",
            "node_id": target["id"],
            "rules": ["DOMAIN-SUFFIX,youtube.com"],
        },
    )
    assert created.status_code == 201

    subscription = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={
            "name": "limited",
            "include_all_nodes": False,
            "node_ids": [included["id"]],
        },
    ).json()["subscription"]
    preview = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/preview?format=clash",
        headers=admin_headers,
    ).json()
    assert yaml.safe_load(preview["content"])["rules"] == ["MATCH,Proxy"]
    assert "not in this subscription" in preview["warnings"][0]


def test_rule_rejects_embedded_policy(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "invalid",
            "target_mode": "direct",
            "rules": ["DOMAIN-SUFFIX,example.com,Proxy"],
        },
    )
    assert response.status_code == 422


def test_group_target_and_direct_rules_are_generated_in_priority_order(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    group = client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={
            "name": "AI 高纯净度",
            "description": "Clean IP nodes",
            "sort_order": 0,
        },
    )
    assert group.status_code == 201
    group_id = group.json()["id"]
    ai_node = _create_node(client, admin_headers, "Clean AI", 4, [group_id])
    _create_node(client, admin_headers, "General", 5)

    direct = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "China direct",
            "target_mode": "direct",
            "rules": ["GEOSITE,cn", "GEOIP,CN,no-resolve"],
            "sort_order": -300,
        },
    )
    assert direct.status_code == 201
    grouped = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "AI",
            "target_mode": "group",
            "group_id": group_id,
            "rules": ["DOMAIN-SUFFIX,openai.com"],
            "sort_order": -200,
        },
    )
    assert grouped.status_code == 201
    assert grouped.json()["target_group_name"] == "AI 高纯净度"

    subscription = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={"name": "all", "include_all_nodes": True},
    ).json()["subscription"]
    preview = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/preview?format=clash",
        headers=admin_headers,
    ).json()
    document = yaml.safe_load(preview["content"])
    ai_group = next(item for item in document["proxy-groups"] if item["name"] == "AI 高纯净度")
    assert ai_group == {
        "name": "AI 高纯净度",
        "type": "select",
        "proxies": [ai_node["name"]],
    }
    assert document["rules"] == [
        "GEOSITE,cn,DIRECT",
        "GEOIP,CN,DIRECT,no-resolve",
        "DOMAIN-SUFFIX,openai.com,AI 高纯净度",
        "MATCH,Proxy",
    ]


def test_group_target_without_included_members_is_skipped(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    group = client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={"name": "Clean", "description": None, "sort_order": 0},
    ).json()
    _create_node(client, admin_headers, "Grouped", 6, [group["id"]])
    included = _create_node(client, admin_headers, "Included", 7)
    created = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "AI",
            "target_mode": "group",
            "group_id": group["id"],
            "rules": ["DOMAIN-SUFFIX,openai.com"],
        },
    )
    assert created.status_code == 201

    subscription = client.post(
        "/api/v1/subscriptions",
        headers=admin_headers,
        json={
            "name": "limited group",
            "include_all_nodes": False,
            "node_ids": [included["id"]],
        },
    ).json()["subscription"]
    preview = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/preview?format=clash",
        headers=admin_headers,
    ).json()
    assert yaml.safe_load(preview["content"])["rules"] == ["MATCH,Proxy"]
    assert "has no nodes in this subscription" in preview["warnings"][0]
