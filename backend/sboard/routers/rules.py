from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sboard.database import get_db
from sboard.models import Group, Node, RuleSet
from sboard.schemas import RuleSetCreate, RuleSetRead, RuleSetUpdate
from sboard.security import require_admin

from .helpers import not_found

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(require_admin)])


def _rule_statement():  # type: ignore[no-untyped-def]
    return select(RuleSet).options(
        selectinload(RuleSet.target_node), selectinload(RuleSet.target_group)
    )


def _rule_to_read(rule: RuleSet) -> RuleSetRead:
    return RuleSetRead(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        target_mode=rule.target_mode,
        node_id=rule.node_id,
        target_node_name=rule.target_node.name if rule.target_node else None,
        group_id=rule.group_id,
        target_group_name=rule.target_group.name if rule.target_group else None,
        rules=rule.rules_json or [],
        sort_order=rule.sort_order,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _resolve_target(
    db: Session,
    target_mode: str,
    node_id: str | None,
    group_id: str | None,
) -> tuple[Node | None, Group | None]:
    if target_mode == "node":
        if not node_id or group_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "node_required", "message": "Node target requires node_id"},
            )
        node = db.get(Node, node_id)
        if node is None:
            raise not_found("node")
        return node, None
    if target_mode == "group":
        if not group_id or node_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "group_required", "message": "Group target requires group_id"},
            )
        group = db.get(Group, group_id)
        if group is None:
            raise not_found("group")
        return None, group
    if node_id or group_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "target_not_allowed",
                "message": "DIRECT and REJECT targets cannot have node_id or group_id",
            },
        )
    return None, None


@router.get("", response_model=list[RuleSetRead])
def list_rules(db: Session = Depends(get_db)) -> list[RuleSetRead]:
    rules = db.scalars(
        _rule_statement().order_by(RuleSet.sort_order, RuleSet.name, RuleSet.id)
    ).all()
    return [_rule_to_read(rule) for rule in rules]


@router.post("", response_model=RuleSetRead, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleSetCreate, db: Session = Depends(get_db)) -> RuleSetRead:
    target_node, target_group = _resolve_target(
        db, payload.target_mode, payload.node_id, payload.group_id
    )
    rule = RuleSet(
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        target_mode=payload.target_mode,
        target_node=target_node,
        target_group=target_group,
        rules_json=payload.rules,
        sort_order=payload.sort_order,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_to_read(rule)


@router.get("/{rule_id}", response_model=RuleSetRead)
def get_rule(rule_id: str, db: Session = Depends(get_db)) -> RuleSetRead:
    rule = db.scalar(_rule_statement().where(RuleSet.id == rule_id))
    if rule is None:
        raise not_found("rule")
    return _rule_to_read(rule)


@router.patch("/{rule_id}", response_model=RuleSetRead)
def update_rule(rule_id: str, payload: RuleSetUpdate, db: Session = Depends(get_db)) -> RuleSetRead:
    rule = db.scalar(_rule_statement().where(RuleSet.id == rule_id))
    if rule is None:
        raise not_found("rule")
    changes = payload.model_dump(exclude_unset=True)
    final_mode = changes.get("target_mode", rule.target_mode)
    final_node_id = changes.get("node_id", rule.node_id if final_mode == "node" else None)
    final_group_id = changes.get("group_id", rule.group_id if final_mode == "group" else None)
    target_node, target_group = _resolve_target(db, final_mode, final_node_id, final_group_id)

    if "rules" in changes:
        rule.rules_json = changes.pop("rules")
    changes.pop("node_id", None)
    changes.pop("group_id", None)
    changes.pop("target_mode", None)
    for key, value in changes.items():
        setattr(rule, key, value)
    rule.target_mode = final_mode
    rule.target_node = target_node
    rule.target_group = target_group
    db.commit()
    db.refresh(rule)
    return _rule_to_read(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, db: Session = Depends(get_db)) -> None:
    rule = db.get(RuleSet, rule_id)
    if rule is None:
        raise not_found("rule")
    db.delete(rule)
    db.commit()
