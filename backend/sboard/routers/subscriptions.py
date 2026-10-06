from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sboard.database import get_db
from sboard.models import Subscription
from sboard.schemas import (
    SubscriptionCreate,
    SubscriptionCreateResult,
    SubscriptionPreview,
    SubscriptionRead,
    SubscriptionUpdate,
)
from sboard.security import generate_token, hash_token, require_admin, token_hint
from sboard.services.state import subscription_to_read
from sboard.services.subscriptions import generate_clash, generate_v2ray

from .helpers import not_found, resolve_groups, resolve_nodes, resolve_tags

router = APIRouter(
    prefix="/subscriptions", tags=["subscriptions"], dependencies=[Depends(require_admin)]
)
public_router = APIRouter(prefix="/subscribe", tags=["public subscriptions"])


def _subscription_statement():  # type: ignore[no-untyped-def]
    return select(Subscription).options(
        selectinload(Subscription.nodes),
        selectinload(Subscription.groups),
        selectinload(Subscription.tags),
    )


def _set_relations(db: Session, subscription: Subscription, payload) -> None:  # type: ignore[no-untyped-def]
    subscription.nodes = resolve_nodes(db, payload.node_ids)
    subscription.groups = resolve_groups(db, payload.group_ids)
    subscription.tags = resolve_tags(db, payload.tag_ids)


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(db: Session = Depends(get_db)) -> list[SubscriptionRead]:
    subscriptions = db.scalars(
        _subscription_statement().order_by(Subscription.name, Subscription.id)
    ).all()
    return [subscription_to_read(subscription) for subscription in subscriptions]


@router.post("", response_model=SubscriptionCreateResult, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
) -> SubscriptionCreateResult:
    raw_token = generate_token("sbs")
    subscription = Subscription(
        name=payload.name,
        token_hash=hash_token(raw_token),
        token=raw_token,
        token_hint=token_hint(raw_token),
        enabled=payload.enabled,
        include_all_nodes=payload.include_all_nodes,
        config_json=payload.config,
    )
    _set_relations(db, subscription, payload)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return SubscriptionCreateResult(
        subscription=subscription_to_read(subscription),
        token=raw_token,
        urls={
            "clash": f"/subscribe/clash/{raw_token}",
            "v2ray": f"/subscribe/v2ray/{raw_token}",
        },
    )


@router.get("/{subscription_id}", response_model=SubscriptionRead)
def get_subscription(subscription_id: str, db: Session = Depends(get_db)) -> SubscriptionRead:
    subscription = db.scalar(_subscription_statement().where(Subscription.id == subscription_id))
    if subscription is None:
        raise not_found("subscription")
    return subscription_to_read(subscription)


@router.patch("/{subscription_id}", response_model=SubscriptionRead)
def update_subscription(
    subscription_id: str,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
) -> SubscriptionRead:
    subscription = db.scalar(_subscription_statement().where(Subscription.id == subscription_id))
    if subscription is None:
        raise not_found("subscription")
    changes = payload.model_dump(exclude_unset=True)
    if "node_ids" in changes:
        subscription.nodes = resolve_nodes(db, changes.pop("node_ids"))
    if "group_ids" in changes:
        subscription.groups = resolve_groups(db, changes.pop("group_ids"))
    if "tag_ids" in changes:
        subscription.tags = resolve_tags(db, changes.pop("tag_ids"))
    if "config" in changes:
        subscription.config_json = changes.pop("config")
    for key, value in changes.items():
        setattr(subscription, key, value)
    db.commit()
    db.refresh(subscription)
    return subscription_to_read(subscription)


@router.post("/{subscription_id}/rotate-token")
def rotate_subscription_token(
    subscription_id: str, db: Session = Depends(get_db)
) -> dict[str, object]:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise not_found("subscription")
    raw_token = generate_token("sbs")
    subscription.token_hash = hash_token(raw_token)
    subscription.token = raw_token
    subscription.token_hint = token_hint(raw_token)
    db.commit()
    return {
        "subscription_id": subscription.id,
        "token": raw_token,
        "urls": {
            "clash": f"/subscribe/clash/{raw_token}",
            "v2ray": f"/subscribe/v2ray/{raw_token}",
        },
    }


@router.get("/{subscription_id}/preview", response_model=SubscriptionPreview)
def preview_subscription(
    subscription_id: str,
    format: Literal["clash", "v2ray"] = "clash",
    db: Session = Depends(get_db),
) -> SubscriptionPreview:
    subscription = db.scalar(_subscription_statement().where(Subscription.id == subscription_id))
    if subscription is None:
        raise not_found("subscription")
    if format == "clash":
        generated = generate_clash(db, subscription)
    elif format == "v2ray":
        generated = generate_v2ray(db, subscription)
    else:  # pragma: no cover - exhaustive Literal guard
        raise AssertionError("unsupported subscription format")
    return SubscriptionPreview(
        format=format,
        content=generated.content,
        included_node_ids=generated.node_ids,
        warnings=generated.warnings,
    )


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(subscription_id: str, db: Session = Depends(get_db)) -> None:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise not_found("subscription")
    db.delete(subscription)
    db.commit()


def _public_subscription(db: Session, token: str) -> Subscription:
    subscription = db.scalar(
        _subscription_statement().where(
            Subscription.token_hash == hash_token(token), Subscription.enabled.is_(True)
        )
    )
    if subscription is None:
        raise not_found("subscription")
    return subscription


def _subscription_response(
    *,
    content: str,
    etag: str,
    media_type: str,
    subscription_name: str,
    extension: str,
    if_none_match: str | None,
) -> Response:
    headers = {
        "ETag": f'"{etag}"',
        "Cache-Control": "no-store",
        "Content-Disposition": _content_disposition(subscription_name, extension),
    }
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return PlainTextResponse(content=content, media_type=media_type, headers=headers)


def _subscription_filename(name: str, extension: str) -> tuple[str, str]:
    display_name = name.strip() or "SBoard"
    full_name = (
        display_name if display_name.lower().endswith(extension) else f"{display_name}{extension}"
    )
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", display_name).strip("-._") or "sboard"
    fallback = ascii_stem if ascii_stem.lower().endswith(extension) else f"{ascii_stem}{extension}"
    return fallback, quote(full_name, safe="")


def _content_disposition(name: str, extension: str) -> str:
    fallback, encoded = _subscription_filename(name, extension)
    # Keep the ASCII fallback unquoted for Clash Verge Rev compatibility.
    # filename* carries the exact UTF-8 name for clients that support RFC 5987.
    return f"attachment; filename={fallback}; filename*=UTF-8''{encoded}"


@public_router.get("/clash/{token}")
def public_clash_subscription(
    token: str,
    if_none_match: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    subscription = _public_subscription(db, token)
    generated = generate_clash(db, subscription)
    subscription.last_access_at = datetime.now(UTC)
    db.commit()
    return _subscription_response(
        content=generated.content,
        etag=generated.etag,
        media_type="text/yaml",
        subscription_name=subscription.name,
        # Clash Verge uses the response filename as the profile's display
        # name, so keep it identical to the name configured in SBoard.
        extension="",
        if_none_match=if_none_match,
    )


@public_router.get("/v2ray/{token}")
def public_v2ray_subscription(
    token: str,
    if_none_match: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    subscription = _public_subscription(db, token)
    generated = generate_v2ray(db, subscription)
    subscription.last_access_at = datetime.now(UTC)
    db.commit()
    return _subscription_response(
        content=generated.content,
        etag=generated.etag,
        media_type="text/plain",
        subscription_name=subscription.name,
        extension=".txt",
        if_none_match=if_none_match,
    )
