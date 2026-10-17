"""One-time conversion of the former mixed presets to individual Geosite rules."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sboard.models import DataMigration, Group, RuleSet

MIGRATION_ID = "20261017_individual_geosite_rules"
logger = logging.getLogger(__name__)

# Untagged presets from early versions are recognized by both name and content.
LEGACY_PRESETS = {
    "ai": ("AI 高纯净度", "DOMAIN-SUFFIX,openai.com"),
    "nsfw": ("NSFW 大流量", "DOMAIN-SUFFIX,missav.ws"),
    "static": ("Static 静态资源与下载", "DOMAIN-SUFFIX,jsdelivr.net"),
    "bulk": ("大流量与开发站点", "DOMAIN-SUFFIX,youtube.com"),
    "china": ("中国大陆与局域网", "GEOSITE,cn"),
    "private": ("局域网直连", "GEOSITE,private"),
    "crypto": ("Crypto 稳定出口（可选）", "GEOSITE,category-cryptocurrency"),
    "ads": ("广告拦截（可选）", "GEOSITE,category-ads-all"),
}

# code, description, target role, priority, row to reuse (if any)
CATEGORIES = [
    ("private", "局域网域名直连", "direct", -900, "private"),
    ("category-ads-all", "广告域名拦截（可选，默认关闭）", "reject", -800, "ads"),
    ("category-ai-!cn", "海外 AI 服务", "ai", -700, "ai"),
    ("category-cryptocurrency", "加密货币服务；主策略建议固定节点", "proxy", -600, "crypto"),
    ("category-porn", "成人内容", "bulk", -500, "nsfw"),
    ("category-cdn-!cn", "海外 CDN 与静态资源", "bulk", -400, "static"),
    ("category-dev", "开发工具、软件仓库与包管理资源", "bulk", -300, None),
    ("category-entertainment", "海外视频、音乐与娱乐", "bulk", -200, "bulk"),
    ("cn", "中国大陆域名直连", "direct", -100, "china"),
]


def _target_group(db: Session, sources: list[RuleSet], aliases: set[str]) -> Group | None:
    ids = {rule.group_id for rule in sources if rule.target_mode == "group" and rule.group_id}
    if len(ids) == 1:
        existing = db.get(Group, next(iter(ids)))
        if existing is not None:
            return existing
    matches = [
        group
        for group in db.scalars(select(Group)).all()
        if "".join(group.name.lower().split()) in aliases
    ]
    return matches[0] if len(matches) == 1 else None


def migrate_geosite_rules(db: Session) -> bool:
    if db.get(DataMigration, MIGRATION_ID) is not None:
        return False
    # Fresh installations get no seeded rules. Only the known old presets are converted.
    rules = (
        list(db.scalars(select(RuleSet).order_by(RuleSet.created_at, RuleSet.id)).all())
        if db.scalar(select(func.count()).select_from(RuleSet))
        else []
    )
    legacy: dict[str, RuleSet] = {}
    for key, (name, sentinel) in LEGACY_PRESETS.items():
        tagged = [rule for rule in rules if rule.template_key == key]
        candidates = tagged or [
            rule
            for rule in rules
            if rule.template_key is None
            and rule.name == name
            and sentinel in (rule.rules_json or [])
        ]
        if len(candidates) == 1:
            legacy[key] = candidates[0]
    if not any(key in legacy for key in ("ai", "nsfw", "static", "bulk", "china", "private")):
        db.add(DataMigration(id=MIGRATION_ID, details_json={"converted": False}))
        db.commit()
        return False
    ai = _target_group(
        db,
        [legacy["ai"]] if "ai" in legacy else [],
        {"ai", "ai组", "ai高纯净度", "高纯净度", "人工智能"},
    )
    bulk = _target_group(
        db,
        [legacy[key] for key in ["nsfw", "static", "bulk"] if key in legacy],
        {"大流量", "大流量组", "bulk", "通用", "通用代理"},
    )
    if ai is None or bulk is None:
        logger.warning("Geosite conversion deferred: AI or bulk target group is missing/ambiguous")
        return False
    originals = [
        {
            "id": rule.id,
            "template_key": rule.template_key,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "target_mode": rule.target_mode,
            "node_id": rule.node_id,
            "group_id": rule.group_id,
            "rules": rule.rules_json,
            "sort_order": rule.sort_order,
        }
        for rule in legacy.values()
    ]
    converted: list[RuleSet] = []
    for code, description, role, priority, source_key in CATEGORIES:
        source = legacy.get(source_key) if source_key else legacy.get("static", legacy.get("bulk"))
        if code == "private" and source is None:
            source = legacy.get("china")
        rule = legacy.get(source_key) if source_key else None
        if rule is None:
            rule = RuleSet()
            db.add(rule)
        rule.name = code
        rule.description = description
        rule.template_key = f"geosite/{code}"
        rule.rules_json = [f"GEOSITE,{code}"]
        if code in {"private", "cn"}:
            rule.rules_json += [f"GEOIP,{'CN' if code == 'cn' else 'private'},no-resolve"]
        rule.enabled = source.enabled if source is not None else role != "reject"
        rule.sort_order = priority
        rule.target_node = None
        rule.target_mode = "group" if role in {"ai", "bulk"} else role
        rule.target_group = ai if role == "ai" else bulk if role == "bulk" else None
        converted.append(rule)
    db.flush()
    db.add(
        DataMigration(
            id=MIGRATION_ID,
            details_json={
                "converted": True,
                "original_rules": originals,
                "category_rule_ids": [rule.id for rule in converted],
            },
        )
    )
    db.commit()
    return True
