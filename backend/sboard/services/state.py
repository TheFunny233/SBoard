from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sboard.config import get_settings
from sboard.models import Agent, Node, Subscription
from sboard.schemas import AgentRead, NodeRead, SubscriptionRead


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def agent_is_online(agent: Agent, now: datetime | None = None) -> bool:
    if not agent.enabled or agent.last_seen_at is None:
        return False
    current = now or datetime.now(UTC)
    threshold = timedelta(seconds=get_settings().offline_threshold_seconds)
    return current - _aware(agent.last_seen_at) <= threshold


def agent_to_read(agent: Agent) -> AgentRead:
    return AgentRead(
        id=agent.id,
        name=agent.name,
        enabled=agent.enabled,
        online=agent_is_online(agent),
        version=agent.version,
        protocol_version=agent.protocol_version,
        last_seen_at=agent.last_seen_at,
        last_ip=agent.last_ip,
        cpu_percent=agent.cpu_percent,
        memory_used_bytes=agent.memory_used_bytes,
        memory_total_bytes=agent.memory_total_bytes,
        uptime_seconds=agent.uptime_seconds,
        xray_status=agent.xray_status,
        xray_version=agent.xray_version,
        xray_message=agent.xray_message,
        xray_ports=agent.xray_ports or [],
        xray_nodes=(agent.extra_json or {}).get("xray_nodes", []),
        desired_config_version=agent.desired_config_version,
        applied_config_version=agent.applied_config_version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def node_online_status(node: Node) -> str:
    if node.source_type == "external" or node.agent is None:
        return "unknown"
    if agent_is_online(node.agent) and node.agent.xray_status == "running":
        return "online"
    return "offline"


def node_to_read(node: Node) -> NodeRead:
    return NodeRead(
        id=node.id,
        source_type=node.source_type,
        agent_id=node.agent_id,
        name=node.name,
        address=node.address,
        port=node.port,
        protocol=node.protocol,
        uuid=node.uuid,
        password=node.password,
        cipher=node.cipher,
        tls=node.tls,
        reality=node.reality,
        sni=node.sni,
        public_key=node.public_key,
        short_id=node.short_id,
        flow=node.flow,
        network=node.network,
        security=node.security,
        path=node.path,
        host=node.host,
        service_name=node.service_name,
        enabled=node.enabled,
        sort_order=node.sort_order,
        extra=node.extra_json or {},
        group_ids=[group.id for group in node.groups],
        tag_ids=[tag.id for tag in node.tags],
        online_status=node_online_status(node),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def subscription_to_read(subscription: Subscription) -> SubscriptionRead:
    return SubscriptionRead(
        id=subscription.id,
        name=subscription.name,
        enabled=subscription.enabled,
        include_all_nodes=subscription.include_all_nodes,
        node_ids=[node.id for node in subscription.nodes],
        group_ids=[group.id for group in subscription.groups],
        tag_ids=[tag.id for tag in subscription.tags],
        config=subscription.config_json or {},
        token_hint=subscription.token_hint,
        last_access_at=subscription.last_access_at,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )
