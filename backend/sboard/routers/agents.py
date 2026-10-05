from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sboard.config import get_settings
from sboard.database import get_db
from sboard.models import Agent, Node
from sboard.schemas import AgentCreate, AgentCreateResult, AgentRead, AgentUpdate
from sboard.security import generate_token, hash_token, require_admin
from sboard.services.state import agent_is_online, agent_to_read

from .helpers import not_found

router = APIRouter(prefix="/agents", tags=["agents"], dependencies=[Depends(require_admin)])


@router.get("")
def list_agents(
    online: bool | None = None,
    enabled: bool | None = None,
    xray_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    statement = select(Agent).order_by(Agent.name, Agent.id)
    if enabled is not None:
        statement = statement.where(Agent.enabled.is_(enabled))
    if xray_status:
        statement = statement.where(Agent.xray_status == xray_status)
    agents = list(db.scalars(statement).all())
    if online is not None:
        agents = [agent for agent in agents if agent_is_online(agent) is online]
    total = len(agents)
    start = (page - 1) * page_size
    return {
        "items": [agent_to_read(agent) for agent in agents[start : start + page_size]],
        "total": total,
    }


@router.post("", response_model=AgentCreateResult, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentCreateResult:
    raw_token = generate_token("sba")
    agent = Agent(name=payload.name, token_hash=hash_token(raw_token))
    db.add(agent)
    db.commit()
    db.refresh(agent)
    server_url = str(request.base_url).rstrip("/")
    return AgentCreateResult(
        agent=agent_to_read(agent),
        token=raw_token,
        config={
            "server_url": server_url,
            "node_id": agent.id,
            "token": raw_token,
            "heartbeat_interval": get_settings().heartbeat_interval_seconds,
            "xray_binary": "/usr/local/bin/xray",
            "xray_config": "/etc/xray/config.json",
            "xray_service": "xray",
            "tls_verify": True,
        },
    )


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentRead:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    return agent_to_read(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
) -> AgentRead:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent_to_read(agent)


@router.post("/{agent_id}/rotate-token")
def rotate_agent_token(agent_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    raw_token = generate_token("sba")
    agent.token_hash = hash_token(raw_token)
    db.commit()
    return {"agent_id": agent.id, "token": raw_token}


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, db: Session = Depends(get_db)) -> None:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    node_count = (
        db.scalar(select(func.count()).select_from(Node).where(Node.agent_id == agent.id)) or 0
    )
    if node_count:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_has_nodes",
                "message": "Delete or move managed nodes before deleting the agent",
            },
        )
    db.delete(agent)
    db.commit()
