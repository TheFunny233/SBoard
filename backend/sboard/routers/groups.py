from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sboard.database import get_db
from sboard.models import Group, Tag
from sboard.schemas import (
    GroupCreate,
    GroupRead,
    GroupUpdate,
    TagCreate,
    TagRead,
    TagUpdate,
)
from sboard.security import require_admin

from .helpers import conflict, not_found

router = APIRouter(tags=["groups"], dependencies=[Depends(require_admin)])


@router.get("/groups", response_model=list[GroupRead])
def list_groups(db: Session = Depends(get_db)) -> list[Group]:
    return list(db.scalars(select(Group).order_by(Group.sort_order, Group.name)).all())


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_db)) -> Group:
    group = Group(**payload.model_dump())
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("group_name_exists", "Group name already exists") from exc
    db.refresh(group)
    return group


@router.patch("/groups/{group_id}", response_model=GroupRead)
def update_group(group_id: str, payload: GroupUpdate, db: Session = Depends(get_db)) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise not_found("group")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("group_name_exists", "Group name already exists") from exc
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: str, db: Session = Depends(get_db)) -> None:
    group = db.get(Group, group_id)
    if group is None:
        raise not_found("group")
    db.delete(group)
    db.commit()


@router.get("/tags", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db)) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())


@router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, db: Session = Depends(get_db)) -> Tag:
    tag = Tag(**payload.model_dump())
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("tag_name_exists", "Tag name already exists") from exc
    db.refresh(tag)
    return tag


@router.patch("/tags/{tag_id}", response_model=TagRead)
def update_tag(tag_id: str, payload: TagUpdate, db: Session = Depends(get_db)) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise not_found("tag")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("tag_name_exists", "Tag name already exists") from exc
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: str, db: Session = Depends(get_db)) -> None:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise not_found("tag")
    db.delete(tag)
    db.commit()
