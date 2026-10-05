from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sboard.database import get_db
from sboard.models import Group, Node, Tag
from sboard.schemas import (
    NodeBatchDelete,
    NodeBatchDeleteResult,
    NodeCreate,
    NodeRead,
    NodeUpdate,
    validate_node_requirements,
)
from sboard.security import require_admin
from sboard.services.state import node_online_status, node_to_read

from .helpers import not_found, resolve_agent, resolve_groups, resolve_tags

router = APIRouter(prefix="/nodes", tags=["nodes"], dependencies=[Depends(require_admin)])


def _node_statement():  # type: ignore[no-untyped-def]
    return select(Node).options(
        selectinload(Node.agent), selectinload(Node.groups), selectinload(Node.tags)
    )


@router.get("")
def list_nodes(
    source_type: str | None = None,
    agent_id: str | None = None,
    protocol: str | None = None,
    group_id: str | None = None,
    tag_id: str | None = None,
    enabled: bool | None = None,
    online: bool | None = None,
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    statement = _node_statement().order_by(Node.sort_order, Node.name, Node.id)
    if source_type:
        statement = statement.where(Node.source_type == source_type)
    if agent_id:
        statement = statement.where(Node.agent_id == agent_id)
    if protocol:
        statement = statement.where(Node.protocol == protocol)
    if group_id:
        statement = statement.where(Node.groups.any(Group.id == group_id))
    if tag_id:
        statement = statement.where(Node.tags.any(Tag.id == tag_id))
    if enabled is not None:
        statement = statement.where(Node.enabled.is_(enabled))
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(Node.name.like(pattern) | Node.address.like(pattern))
    nodes = list(db.scalars(statement).all())
    if online is not None:
        desired = "online" if online else "offline"
        nodes = [node for node in nodes if node_online_status(node) == desired]
    total = len(nodes)
    start = (page - 1) * page_size
    return {
        "items": [node_to_read(node) for node in nodes[start : start + page_size]],
        "total": total,
    }


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)) -> NodeRead:
    agent = resolve_agent(db, payload.agent_id)
    groups = resolve_groups(db, payload.group_ids)
    tags = resolve_tags(db, payload.tag_ids)
    data = payload.model_dump(exclude={"group_ids", "tag_ids", "extra"})
    node = Node(**data, extra_json=payload.extra, agent=agent, groups=groups, tags=tags)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node_to_read(node)


@router.delete("/batch", response_model=NodeBatchDeleteResult)
def delete_nodes(
    payload: NodeBatchDelete, db: Session = Depends(get_db)
) -> NodeBatchDeleteResult:
    nodes = list(db.scalars(select(Node).where(Node.id.in_(payload.ids))).all())
    found_ids = {node.id for node in nodes}
    for node in nodes:
        db.delete(node)
    db.commit()
    return NodeBatchDeleteResult(
        deleted=len(nodes),
        missing_ids=[node_id for node_id in payload.ids if node_id not in found_ids],
    )


@router.get("/{node_id}", response_model=NodeRead)
def get_node(node_id: str, db: Session = Depends(get_db)) -> NodeRead:
    node = db.scalar(_node_statement().where(Node.id == node_id))
    if node is None:
        raise not_found("node")
    return node_to_read(node)


@router.patch("/{node_id}", response_model=NodeRead)
def update_node(node_id: str, payload: NodeUpdate, db: Session = Depends(get_db)) -> NodeRead:
    node = db.scalar(_node_statement().where(Node.id == node_id))
    if node is None:
        raise not_found("node")

    changes = payload.model_dump(exclude_unset=True)
    group_ids = changes.pop("group_ids", None)
    tag_ids = changes.pop("tag_ids", None)
    extra = changes.pop("extra", None)

    final_source = changes.get("source_type", node.source_type)
    if "agent_id" in changes:
        final_agent_id = changes["agent_id"]
    elif final_source == "external":
        final_agent_id = None
    else:
        final_agent_id = node.agent_id
    if final_source == "managed" and not final_agent_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "agent_required", "message": "Managed nodes require agent_id"},
        )
    if final_source == "external" and final_agent_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "agent_not_allowed", "message": "External nodes cannot have agent_id"},
        )
    final_protocol = changes.get("protocol", node.protocol)
    final_uuid = changes.get("uuid", node.uuid)
    final_password = changes.get("password", node.password)
    final_cipher = changes.get("cipher", node.cipher)
    try:
        validate_node_requirements(final_protocol, final_uuid, final_password, final_cipher)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_protocol_fields", "message": str(exc)},
        ) from exc

    if final_agent_id != node.agent_id:
        node.agent = resolve_agent(db, final_agent_id)
        changes.pop("agent_id", None)
    elif "agent_id" in changes:
        changes.pop("agent_id")
    for key, value in changes.items():
        setattr(node, key, value)
    if extra is not None:
        node.extra_json = extra
    if group_ids is not None:
        node.groups = resolve_groups(db, group_ids)
    if tag_ids is not None:
        node.tags = resolve_tags(db, tag_ids)

    db.commit()
    db.refresh(node)
    return node_to_read(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, db: Session = Depends(get_db)) -> None:
    node = db.get(Node, node_id)
    if node is None:
        raise not_found("node")
    db.delete(node)
    db.commit()
