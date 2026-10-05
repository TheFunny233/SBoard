from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from sboard.database import get_db
from sboard.models import Node
from sboard.schemas import ImportItem, ImportRequest, ImportResult, NodeCreate
from sboard.security import require_admin
from sboard.services.importer import ImportParseError, parse_share_link

from .helpers import resolve_groups, resolve_tags

router = APIRouter(tags=["imports"], dependencies=[Depends(require_admin)])


def _duplicate_key(node: dict[str, Any]) -> tuple[object, ...]:
    return (
        node.get("protocol"),
        node.get("address"),
        node.get("port"),
        node.get("uuid"),
        node.get("password"),
        node.get("cipher"),
    )


@router.post("/nodes/import", response_model=ImportResult)
def import_nodes(payload: ImportRequest, db: Session = Depends(get_db)) -> ImportResult:
    groups = resolve_groups(db, payload.group_ids)
    tags = resolve_tags(db, payload.tag_ids)
    items: list[ImportItem] = []
    valid: list[tuple[int, NodeCreate]] = []

    for index, link in enumerate(payload.links):
        try:
            parsed = parse_share_link(link)
            parsed["group_ids"] = payload.group_ids
            parsed["tag_ids"] = payload.tag_ids
            node_payload = NodeCreate.model_validate(parsed)
            valid.append((index, node_payload))
            items.append(ImportItem(index=index, status="valid", node=node_payload.model_dump()))
        except (ImportParseError, ValidationError, ValueError) as exc:
            items.append(ImportItem(index=index, status="error", error=str(exc)))

    failed = sum(item.status == "error" for item in items)
    if payload.mode == "preview":
        return ImportResult(
            mode=payload.mode, total=len(items), created=0, failed=failed, items=items
        )
    if failed and payload.atomic:
        for item in items:
            if item.status == "valid":
                item.warning = "Atomic import was not committed because another item failed"
        return ImportResult(
            mode=payload.mode, total=len(items), created=0, failed=failed, items=items
        )

    existing_nodes = list(db.scalars(select(Node)).all())
    known_keys = {
        _duplicate_key(
            {
                "protocol": node.protocol,
                "address": node.address,
                "port": node.port,
                "uuid": node.uuid,
                "password": node.password,
                "cipher": node.cipher,
            }
        )
        for node in existing_nodes
    }
    created = 0
    item_by_index = {item.index: item for item in items}
    for index, node_payload in valid:
        item = item_by_index[index]
        data = node_payload.model_dump(exclude={"group_ids", "tag_ids", "extra"})
        key = _duplicate_key(data)
        if payload.duplicate_policy == "skip" and key in known_keys:
            item.status = "skipped"
            item.warning = "Duplicate node"
            continue
        node = Node(
            **data,
            extra_json=node_payload.extra,
            groups=list(groups),
            tags=list(tags),
        )
        db.add(node)
        db.flush()
        known_keys.add(key)
        item.status = "created"
        item.node_id = node.id
        created += 1
    db.commit()
    return ImportResult(
        mode=payload.mode, total=len(items), created=created, failed=failed, items=items
    )
