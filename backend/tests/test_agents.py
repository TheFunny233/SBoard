from datetime import UTC, datetime

from fastapi.testclient import TestClient


def test_admin_api_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/agents")
    assert response.status_code == 401


def test_agent_creation_and_heartbeat(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post("/api/v1/agents", headers=admin_headers, json={"name": "hk-edge-1"})
    assert created.status_code == 201
    result = created.json()
    agent_id = result["agent"]["id"]
    agent_token = result["token"]
    assert result["config"]["node_id"] == agent_id
    assert result["config"]["token"] == agent_token

    heartbeat = client.post(
        "/api/node/v1/heartbeat",
        headers={"Authorization": f"Bearer {agent_token}"},
        json={
            "schema_version": 1,
            "node_id": agent_id,
            "version": "0.1.0",
            "sent_at": datetime.now(UTC).isoformat(),
            "boot_id": "boot-1",
            "seq": 1,
            "cpu_percent": 2.5,
            "memory_used_bytes": 10_000_000,
            "memory_total_bytes": 128_000_000,
            "uptime_seconds": 60,
            "xray_status": "running",
            "xray_version": "25.1.1",
            "xray_ports": [443],
            "capabilities": ["heartbeat"],
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["accepted"] is True

    detail = client.get(f"/api/v1/agents/{agent_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["online"] is True
    assert detail.json()["xray_status"] == "running"
    assert detail.json()["memory_total_bytes"] == 128_000_000


def test_agent_token_cannot_impersonate_another_agent(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    first = client.post("/api/v1/agents", headers=admin_headers, json={"name": "first"}).json()
    second = client.post("/api/v1/agents", headers=admin_headers, json={"name": "second"}).json()
    response = client.post(
        "/api/node/v1/heartbeat",
        headers={"Authorization": f"Bearer {first['token']}"},
        json={
            "node_id": second["agent"]["id"],
            "version": "0.1.0",
            "sent_at": datetime.now(UTC).isoformat(),
            "boot_id": "boot-1",
            "seq": 1,
            "cpu_percent": 1,
            "memory_used_bytes": 1,
            "memory_total_bytes": 128_000_000,
            "uptime_seconds": 1,
            "xray_status": "unknown",
        },
    )
    assert response.status_code == 403
