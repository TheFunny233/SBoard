from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sboard.models import Group, Node, Tag
from sboard.schemas import BackupGroup, BackupTag, NodeBackup, NodeCreate


def all_nodes(db: Session) -> list[Node]:
    # No subscription selection, pagination, enabled filter, or TCP probes.
    return list(
        db.scalars(
            select(Node)
            .options(selectinload(Node.groups), selectinload(Node.tags))
            .order_by(Node.sort_order, Node.name, Node.id)
        ).all()
    )


def backup_nodes(db: Session) -> NodeBackup:
    nodes = []
    for node in all_nodes(db):
        data = {
            key: getattr(node, key)
            for key in NodeCreate.model_fields
            if key not in {"extra", "group_ids", "tag_ids"}
        }
        nodes.append(
            NodeCreate(
                **data,
                extra=node.extra_json or {},
                group_ids=[group.id for group in node.groups],
                tag_ids=[tag.id for tag in node.tags],
            )
        )
    return NodeBackup(
        nodes=nodes,
        groups=[BackupGroup.model_validate(group) for group in db.scalars(select(Group)).all()],
        tags=[BackupTag.model_validate(tag) for tag in db.scalars(select(Tag)).all()],
    )
