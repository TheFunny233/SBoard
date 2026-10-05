from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from sboard.config import get_settings
from sboard.database import get_db
from sboard.models import Agent
from sboard.schemas import HeartbeatRequest, HeartbeatResponse
from sboard.security import require_agent

router = APIRouter(prefix="/node/v1", tags=["agent protocol"])


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    if payload.schema_version != 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_schema_version",
                "message": "Only heartbeat schema version 1 is supported",
            },
        )
    if payload.node_id != agent.id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "agent_identity_mismatch",
                "message": "Token does not belong to the supplied node_id",
            },
        )

    stale = (
        agent.boot_id == payload.boot_id
        and agent.heartbeat_seq is not None
        and payload.seq <= agent.heartbeat_seq
    )
    agent.last_seen_at = datetime.now(UTC)
    agent.last_ip = request.client.host if request.client else None
    if not stale:
        agent.version = payload.version
        agent.protocol_version = payload.schema_version
        agent.cpu_percent = payload.cpu_percent
        agent.memory_used_bytes = payload.memory_used_bytes
        agent.memory_total_bytes = payload.memory_total_bytes
        agent.uptime_seconds = payload.uptime_seconds
        agent.xray_status = payload.xray_status
        agent.xray_version = payload.xray_version
        agent.xray_message = payload.xray_message
        agent.xray_ports = payload.xray_ports
        agent.boot_id = payload.boot_id
        agent.heartbeat_seq = payload.seq
        agent.applied_config_version = payload.applied_config_version
        agent.applied_config_hash = payload.applied_config_hash
        agent.extra_json = {
            "xray_pid": payload.xray_pid,
            "restart_count": payload.restart_count,
            "capabilities": payload.capabilities,
            "xray_nodes": [node.model_dump(exclude_none=True) for node in payload.xray_nodes],
        }
    db.commit()

    settings = get_settings()
    return HeartbeatResponse(
        accepted=True,
        server_time=datetime.now(UTC),
        next_heartbeat_seconds=settings.heartbeat_interval_seconds,
        desired_config_version=agent.desired_config_version,
        config_changed=agent.desired_config_version > payload.applied_config_version,
    )
