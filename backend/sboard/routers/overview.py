from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sboard.database import get_db
from sboard.models import Agent, Node, Subscription
from sboard.schemas import OverviewResponse
from sboard.security import require_admin
from sboard.services.state import agent_is_online

router = APIRouter(tags=["overview"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=OverviewResponse)
def overview(db: Session = Depends(get_db)) -> OverviewResponse:
    agents = list(db.scalars(select(Agent)).all())
    agents_online = sum(agent_is_online(agent) for agent in agents)
    protocol_rows = db.execute(
        select(Node.protocol, func.count(Node.id)).group_by(Node.protocol)
    ).all()
    return OverviewResponse(
        agents_total=len(agents),
        agents_online=agents_online,
        agents_offline=len(agents) - agents_online,
        managed_nodes=db.scalar(
            select(func.count()).select_from(Node).where(Node.source_type == "managed")
        )
        or 0,
        external_nodes=db.scalar(
            select(func.count()).select_from(Node).where(Node.source_type == "external")
        )
        or 0,
        subscriptions=db.scalar(select(func.count()).select_from(Subscription)) or 0,
        nodes_by_protocol={protocol: count for protocol, count in protocol_rows},
    )
