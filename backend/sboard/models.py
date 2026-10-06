from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sboard.database import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


node_groups = Table(
    "node_groups",
    Base.metadata,
    Column("node_id", String(36), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", String(36), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

node_tags = Table(
    "node_tags",
    Base.metadata,
    Column("node_id", String(36), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

subscription_nodes = Table(
    "subscription_nodes",
    Base.metadata,
    Column(
        "subscription_id",
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("node_id", String(36), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
)

subscription_groups = Table(
    "subscription_groups",
    Base.metadata,
    Column(
        "subscription_id",
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("group_id", String(36), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

subscription_tags = Table(
    "subscription_tags",
    Base.metadata,
    Column(
        "subscription_id",
        String(36),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str | None] = mapped_column(String(50))
    protocol_version: Mapped[int] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_ip: Mapped[str | None] = mapped_column(String(64))
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_used_bytes: Mapped[int | None] = mapped_column(Integer)
    memory_total_bytes: Mapped[int | None] = mapped_column(Integer)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    xray_status: Mapped[str] = mapped_column(String(20), default="unknown")
    xray_version: Mapped[str | None] = mapped_column(String(50))
    xray_message: Mapped[str | None] = mapped_column(Text)
    xray_ports: Mapped[list[int]] = mapped_column(JSON, default=list)
    boot_id: Mapped[str | None] = mapped_column(String(100))
    heartbeat_seq: Mapped[int | None] = mapped_column(Integer)
    desired_config_version: Mapped[int] = mapped_column(Integer, default=0)
    applied_config_version: Mapped[int] = mapped_column(Integer, default=0)
    applied_config_hash: Mapped[str | None] = mapped_column(String(64))
    extra_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    nodes: Mapped[list[Node]] = relationship(back_populates="agent")
    config_revisions: Mapped[list[AgentConfigRevision]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_protocol_enabled", "protocol", "enabled"),
        Index("ix_nodes_source_agent", "source_type", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(30), index=True)
    uuid: Mapped[str | None] = mapped_column(String(100))
    password: Mapped[str | None] = mapped_column(Text)
    cipher: Mapped[str | None] = mapped_column(String(100))
    tls: Mapped[bool] = mapped_column(Boolean, default=True)
    reality: Mapped[bool] = mapped_column(Boolean, default=True)
    sni: Mapped[str | None] = mapped_column(String(255))
    public_key: Mapped[str | None] = mapped_column(Text)
    short_id: Mapped[str | None] = mapped_column(String(100))
    flow: Mapped[str | None] = mapped_column(String(100))
    network: Mapped[str | None] = mapped_column(String(50))
    security: Mapped[str | None] = mapped_column(String(50))
    path: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(String(255))
    service_name: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    extra_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    agent: Mapped[Agent | None] = relationship(back_populates="nodes")
    groups: Mapped[list[Group]] = relationship(secondary=node_groups, back_populates="nodes")
    tags: Mapped[list[Tag]] = relationship(secondary=node_tags, back_populates="nodes")
    subscriptions: Mapped[list[Subscription]] = relationship(
        secondary=subscription_nodes, back_populates="nodes"
    )


class RuleSet(TimestampMixin, Base):
    __tablename__ = "rule_sets"
    __table_args__ = (Index("ix_rule_sets_enabled_order", "enabled", "sort_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    target_mode: Mapped[str] = mapped_column(String(20), default="node")
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("nodes.id", ondelete="SET NULL"), index=True
    )
    rules_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    target_node: Mapped[Node | None] = relationship()


class Group(TimestampMixin, Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    nodes: Mapped[list[Node]] = relationship(secondary=node_groups, back_populates="groups")
    subscriptions: Mapped[list[Subscription]] = relationship(
        secondary=subscription_groups, back_populates="groups"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    nodes: Mapped[list[Node]] = relationship(secondary=node_tags, back_populates="tags")
    subscriptions: Mapped[list[Subscription]] = relationship(
        secondary=subscription_tags, back_populates="tags"
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Kept so administrators can retrieve active subscription URLs after creation.
    token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_hint: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    include_all_nodes: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    nodes: Mapped[list[Node]] = relationship(
        secondary=subscription_nodes, back_populates="subscriptions"
    )
    groups: Mapped[list[Group]] = relationship(
        secondary=subscription_groups, back_populates="subscriptions"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=subscription_tags, back_populates="subscriptions"
    )


class AgentConfigRevision(Base):
    __tablename__ = "agent_config_revisions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agent: Mapped[Agent] = relationship(back_populates="config_revisions")
