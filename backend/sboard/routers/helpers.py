from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sboard.models import Agent, Group, Node, Tag

ModelT = TypeVar("ModelT")


def not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": f"{resource}_not_found", "message": f"{resource} not found"},
    )


def conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def resolve_agent(db: Session, agent_id: str | None) -> Agent | None:
    if agent_id is None:
        return None
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    return agent


def _resolve_many(db: Session, model: type[ModelT], ids: Iterable[str], name: str) -> list[ModelT]:
    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return []
    records = list(db.scalars(select(model).where(model.id.in_(unique_ids))).all())  # type: ignore[attr-defined]
    if len(records) != len(unique_ids):
        found = {record.id for record in records}  # type: ignore[attr-defined]
        missing = [item_id for item_id in unique_ids if item_id not in found]
        raise HTTPException(
            status_code=422,
            detail={
                "code": f"invalid_{name}_ids",
                "message": f"Unknown {name} ids",
                "details": missing,
            },
        )
    order = {item_id: index for index, item_id in enumerate(unique_ids)}
    return sorted(records, key=lambda record: order[record.id])  # type: ignore[attr-defined]


def resolve_groups(db: Session, ids: Iterable[str]) -> list[Group]:
    return _resolve_many(db, Group, ids, "group")


def resolve_tags(db: Session, ids: Iterable[str]) -> list[Tag]:
    return _resolve_many(db, Tag, ids, "tag")


def resolve_nodes(db: Session, ids: Iterable[str]) -> list[Node]:
    return _resolve_many(db, Node, ids, "node")
