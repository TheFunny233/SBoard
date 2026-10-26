from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from sboard.database import get_db
from sboard.models import Group, Node, Tag
from sboard.schemas import BackupImportRequest, ImportItem, ImportRequest, ImportResult, NodeCreate
from sboard.security import require_admin
from sboard.services.importer import ImportParseError, parse_share_link

from .helpers import resolve_groups, resolve_tags

router = APIRouter(tags=["imports"], dependencies=[Depends(require_admin)])


def _duplicate_key(node: Node | dict[str, Any]) -> str:
    # The same endpoint/UUID may have distinct transports or download servers.
    fields = set(NodeCreate.model_fields) - {
        "name",
        "source_type",
        "agent_id",
        "enabled",
        "sort_order",
        "group_ids",
        "tag_ids",
    }
    if isinstance(node, Node):
        values = {
            key: (node.extra_json or {}) if key == "extra" else getattr(node, key) for key in fields
        }
    else:
        values = {key: node.get(key) for key in fields}
    return json.dumps(values, sort_keys=True, ensure_ascii=False)


@router.post("/nodes/import-backup", response_model=ImportResult)
def import_backup(payload: BackupImportRequest, db: Session = Depends(get_db)) -> ImportResult:
    items: list[ImportItem] = []
    for index, node in enumerate(payload.backup.nodes):
        data = node.model_dump()
        warning = None
        if node.source_type == "managed":
            data.update(source_type="external", agent_id=None)
            warning = "托管节点作为外部节点恢复；请在新面板重新绑定边缘主机"
        items.append(ImportItem(index=index, status="valid", node=data, warning=warning))
    if payload.mode == "preview":
        return ImportResult(mode=payload.mode, total=len(items), created=0, failed=0, items=items)

    # Reuse names on the destination without overwriting existing taxonomy settings.
    groups = {group.name: group for group in db.scalars(select(Group)).all()}
    tags = {tag.name: tag for tag in db.scalars(select(Tag)).all()}
    group_map = {}
    tag_map = {}
    for record in payload.backup.groups:
        if record.name not in groups:
            group = Group(**record.model_dump(exclude={"id"}))
            db.add(group)
            groups[record.name] = group
        group_map[record.id] = groups[record.name]
    for record in payload.backup.tags:
        if record.name not in tags:
            tag = Tag(**record.model_dump(exclude={"id"}))
            db.add(tag)
            tags[record.name] = tag
        tag_map[record.id] = tags[record.name]
    # Backups preserve repeated records as well as distinct display names. Consume
    # only matches that already existed on the destination before this restore.
    existing = Counter((_duplicate_key(node), node.name) for node in db.scalars(select(Node)).all())
    created = 0
    for item in items:
        data = dict(item.node or {})
        key = (_duplicate_key(data), data["name"])
        if payload.duplicate_policy == "skip" and existing[key] > 0:
            existing[key] -= 1
            item.status = "skipped"
            item.warning = "Duplicate node"
            continue
        node_groups = [group_map[key] for key in set(data.pop("group_ids"))]
        node_tags = [tag_map[key] for key in set(data.pop("tag_ids"))]
        extra = data.pop("extra")
        node = Node(**data, extra_json=extra, groups=node_groups, tags=node_tags)
        db.add(node)
        db.flush()
        item.status = "created"
        item.node_id = node.id
        created += 1
    db.commit()
    return ImportResult(mode=payload.mode, total=len(items), created=created, failed=0, items=items)


@router.post("/nodes/import", response_model=ImportResult)
def import_nodes(payload: ImportRequest, db: Session = Depends(get_db)) -> ImportResult:
    groups = resolve_groups(db, payload.group_ids)
    tags = resolve_tags(db, payload.tag_ids)
    items: list[ImportItem] = []
    valid: list[tuple[int, NodeCreate]] = []

    for index, link in enumerate(payload.links):
        try:
            parsed = parse_share_link(link)
            if payload.name_prefix and parsed.get("name"):
                parsed["name"] = f"{payload.name_prefix.strip()} - {parsed['name']}"
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
    known_keys = {_duplicate_key(node) for node in existing_nodes}
    created = 0
    item_by_index = {item.index: item for item in items}
    for index, node_payload in valid:
        item = item_by_index[index]
        data = node_payload.model_dump(exclude={"group_ids", "tag_ids", "extra"})
        key = _duplicate_key(node_payload.model_dump())
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
