from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProtocolName = Literal[
    "vless",
    "vmess",
    "trojan",
    "ss",
    "ss2022",
    "hysteria2",
    "tuic",
    "wireguard",
]
SourceType = Literal["managed", "external"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


def validate_node_requirements(
    protocol: str,
    uuid: str | None,
    password: str | None,
    cipher: str | None,
) -> None:
    if protocol in {"vless", "vmess"} and not uuid:
        raise ValueError(f"{protocol} nodes require uuid")
    if protocol in {"trojan", "hysteria2"} and not password:
        raise ValueError(f"{protocol} nodes require password")
    if protocol in {"ss", "ss2022"} and (not cipher or not password):
        raise ValueError(f"{protocol} nodes require cipher and password")
    if protocol == "tuic" and (not uuid or not password):
        raise ValueError("tuic nodes require uuid and password")


class AgentCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)


class AgentUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> AgentUpdate:
        for field in {"name", "enabled"} & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AgentRead(ApiModel):
    id: str
    name: str
    enabled: bool
    online: bool
    version: str | None
    protocol_version: int
    last_seen_at: datetime | None
    last_ip: str | None
    cpu_percent: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    uptime_seconds: int | None
    xray_status: str
    xray_version: str | None
    xray_message: str | None
    xray_ports: list[int]
    desired_config_version: int
    applied_config_version: int
    created_at: datetime
    updated_at: datetime


class AgentCreateResult(ApiModel):
    agent: AgentRead
    token: str
    config: dict[str, Any]


class NodeFields(ApiModel):
    source_type: SourceType
    agent_id: str | None = None
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    protocol: ProtocolName
    uuid: str | None = Field(default=None, max_length=100)
    password: str | None = None
    cipher: str | None = Field(default=None, max_length=100)
    tls: bool = False
    reality: bool = False
    sni: str | None = Field(default=None, max_length=255)
    public_key: str | None = None
    short_id: str | None = Field(default=None, max_length=100)
    flow: str | None = Field(default=None, max_length=100)
    network: str | None = Field(default=None, max_length=50)
    security: str | None = Field(default=None, max_length=50)
    path: str | None = None
    host: str | None = Field(default=None, max_length=255)
    service_name: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    sort_order: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)
    group_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source(self) -> NodeFields:
        if self.source_type == "managed" and not self.agent_id:
            raise ValueError("managed nodes require agent_id")
        if self.source_type == "external" and self.agent_id:
            raise ValueError("external nodes cannot have agent_id")
        validate_node_requirements(self.protocol, self.uuid, self.password, self.cipher)
        return self


class NodeCreate(NodeFields):
    pass


class NodeUpdate(ApiModel):
    source_type: SourceType | None = None
    agent_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: ProtocolName | None = None
    uuid: str | None = Field(default=None, max_length=100)
    password: str | None = None
    cipher: str | None = Field(default=None, max_length=100)
    tls: bool | None = None
    reality: bool | None = None
    sni: str | None = Field(default=None, max_length=255)
    public_key: str | None = None
    short_id: str | None = Field(default=None, max_length=100)
    flow: str | None = Field(default=None, max_length=100)
    network: str | None = Field(default=None, max_length=50)
    security: str | None = Field(default=None, max_length=50)
    path: str | None = None
    host: str | None = Field(default=None, max_length=255)
    service_name: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    sort_order: int | None = None
    extra: dict[str, Any] | None = None
    group_ids: list[str] | None = None
    tag_ids: list[str] | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> NodeUpdate:
        required = {
            "source_type",
            "name",
            "address",
            "port",
            "protocol",
            "tls",
            "reality",
            "enabled",
            "sort_order",
            "extra",
            "group_ids",
            "tag_ids",
        }
        for field in required & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NodeRead(NodeFields):
    id: str
    online_status: Literal["online", "offline", "unknown"]
    created_at: datetime
    updated_at: datetime


class NodeBatchDelete(ApiModel):
    ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("ids")
    @classmethod
    def normalize_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class NodeBatchDeleteResult(ApiModel):
    deleted: int
    missing_ids: list[str]


RuleTargetMode = Literal["node", "direct", "reject"]
SUPPORTED_RULE_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "GEOSITE",
    "GEOIP",
    "IP-CIDR",
    "IP-CIDR6",
    "SRC-IP-CIDR",
    "DST-PORT",
    "SRC-PORT",
    "PROCESS-NAME",
    "PROCESS-PATH",
    "NETWORK",
    "IN-TYPE",
}


def normalize_rule_conditions(value: list[str]) -> list[str]:
    rules: list[str] = []
    for raw_rule in value:
        rule = raw_rule.strip()
        if not rule or rule in rules:
            continue
        if len(rule) > 500:
            raise ValueError("each rule must be at most 500 characters")
        parts = [part.strip() for part in rule.split(",")]
        rule_type = parts[0].upper()
        if rule_type not in SUPPORTED_RULE_TYPES:
            raise ValueError(f"unsupported rule type: {parts[0]}")
        if len(parts) not in {2, 3} or not parts[1]:
            raise ValueError(f"invalid rule condition: {rule}")
        if len(parts) == 3 and parts[2].lower() != "no-resolve":
            raise ValueError("do not include a policy; choose the target separately")
        rules.append(",".join([rule_type, *parts[1:]]))
    if not rules:
        raise ValueError("at least one rule is required")
    return rules


class RuleSetCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    target_mode: RuleTargetMode = "node"
    node_id: str | None = None
    rules: list[str] = Field(min_length=1, max_length=200)
    sort_order: int = 0

    @field_validator("rules")
    @classmethod
    def validate_rules(cls, value: list[str]) -> list[str]:
        return normalize_rule_conditions(value)

    @model_validator(mode="after")
    def validate_target(self) -> RuleSetCreate:
        if self.target_mode == "node" and not self.node_id:
            raise ValueError("node target requires node_id")
        if self.target_mode != "node" and self.node_id:
            raise ValueError("DIRECT and REJECT targets cannot have node_id")
        return self


class RuleSetUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    target_mode: RuleTargetMode | None = None
    node_id: str | None = None
    rules: list[str] | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None

    @field_validator("rules")
    @classmethod
    def validate_rules(cls, value: list[str] | None) -> list[str] | None:
        return normalize_rule_conditions(value) if value is not None else value

    @model_validator(mode="after")
    def reject_nulls(self) -> RuleSetUpdate:
        required = {"name", "enabled", "target_mode", "rules", "sort_order"}
        for field in required & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class RuleSetRead(ApiModel):
    id: str
    name: str
    description: str | None
    enabled: bool
    target_mode: RuleTargetMode
    node_id: str | None
    target_node_name: str | None
    rules: list[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime


class GroupCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    sort_order: int = 0


class GroupUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> GroupUpdate:
        for field in {"name", "sort_order"} & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class GroupRead(ApiModel):
    id: str
    name: str
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TagCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)


class TagUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def reject_null_name(self) -> TagUpdate:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class TagRead(ApiModel):
    id: str
    name: str
    color: str | None
    created_at: datetime


class ImportRequest(ApiModel):
    mode: Literal["preview", "commit"] = "preview"
    links: list[str] = Field(min_length=1, max_length=500)
    group_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    duplicate_policy: Literal["skip", "create"] = "skip"
    atomic: bool = True


class ImportItem(ApiModel):
    index: int
    status: Literal["valid", "created", "skipped", "error"]
    node: dict[str, Any] | None = None
    node_id: str | None = None
    warning: str | None = None
    error: str | None = None


class ImportResult(ApiModel):
    mode: str
    total: int
    created: int
    failed: int
    items: list[ImportItem]


def validate_subscription_config(value: dict[str, Any]) -> dict[str, Any]:
    for key in ("group_name", "auto_group_name", "test_url"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(f"config.{key} must be a non-empty string")
    if "test_interval" in value:
        interval = value["test_interval"]
        if (
            isinstance(interval, bool)
            or not isinstance(interval, int)
            or not 30 <= interval <= 86400
        ):
            raise ValueError("config.test_interval must be an integer between 30 and 86400")
    if "include_auto" in value and not isinstance(value["include_auto"], bool):
        raise ValueError("config.include_auto must be a boolean")
    if "rules" in value:
        rules = value["rules"]
        if (
            not isinstance(rules, list)
            or not rules
            or not all(isinstance(rule, str) and rule.strip() for rule in rules)
        ):
            raise ValueError("config.rules must be a non-empty list of strings")
    return value


class SubscriptionFields(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    include_all_nodes: bool = True
    node_ids: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_subscription_config(value)


class SubscriptionCreate(SubscriptionFields):
    pass


class SubscriptionUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    include_all_nodes: bool | None = None
    node_ids: list[str] | None = None
    group_ids: list[str] | None = None
    tag_ids: list[str] | None = None
    config: dict[str, Any] | None = None

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_subscription_config(value) if value is not None else value

    @model_validator(mode="after")
    def reject_nulls(self) -> SubscriptionUpdate:
        required = {
            "name",
            "enabled",
            "include_all_nodes",
            "node_ids",
            "group_ids",
            "tag_ids",
            "config",
        }
        for field in required & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SubscriptionRead(SubscriptionFields):
    id: str
    token_hint: str
    last_access_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubscriptionCreateResult(ApiModel):
    subscription: SubscriptionRead
    token: str
    urls: dict[str, str]


class SubscriptionPreview(ApiModel):
    format: Literal["clash", "v2ray"]
    content: str
    included_node_ids: list[str]
    warnings: list[str]


class HeartbeatRequest(ApiModel):
    schema_version: int = Field(default=1, ge=1)
    node_id: str
    version: str = Field(min_length=1, max_length=50)
    sent_at: datetime
    boot_id: str = Field(min_length=1, max_length=100)
    seq: int = Field(ge=0)
    cpu_percent: float = Field(ge=0, le=100)
    memory_used_bytes: int = Field(ge=0)
    memory_total_bytes: int = Field(gt=0)
    uptime_seconds: int = Field(ge=0)
    xray_status: Literal["running", "stopped", "error", "unknown"]
    xray_version: str | None = Field(default=None, max_length=50)
    xray_pid: int | None = Field(default=None, ge=1)
    xray_ports: list[int] = Field(default_factory=list, max_length=100)
    restart_count: int = Field(default=0, ge=0)
    xray_message: str | None = Field(default=None, max_length=2000)
    applied_config_version: int = Field(default=0, ge=0)
    applied_config_hash: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_memory(self) -> HeartbeatRequest:
        if self.memory_used_bytes > self.memory_total_bytes:
            raise ValueError("memory_used_bytes cannot exceed memory_total_bytes")
        if any(port < 1 or port > 65535 for port in self.xray_ports):
            raise ValueError("xray_ports must contain valid TCP/UDP ports")
        return self


class HeartbeatResponse(ApiModel):
    accepted: bool
    server_time: datetime
    next_heartbeat_seconds: int
    desired_config_version: int
    config_changed: bool


class OverviewResponse(ApiModel):
    agents_total: int
    agents_online: int
    agents_offline: int
    managed_nodes: int
    external_nodes: int
    subscriptions: int
    nodes_by_protocol: dict[str, int]
