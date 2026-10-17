import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from sboard.database import Base
from sboard.models import DataMigration, Group, Node, RuleSet, Subscription
from sboard.services.geosite_migration import MIGRATION_ID, migrate_geosite_rules
from sboard.services.subscriptions import generate_clash


@pytest.fixture
def db():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def seed_legacy(db, tagged=True):  # type: ignore[no-untyped-def]
    ai = Group(name="AI", strategy="url-test")
    bulk = Group(name="大流量", strategy="fallback")
    for group in [ai, bulk]:
        db.add(
            Node(
                name=group.name + " node",
                groups=[group],
                source_type="external",
                address="test.example.com",
                port=443,
                protocol="ss",
                cipher="aes-128-gcm",
                password="test-only",
            )
        )
    originals = [
        ("ai", "AI 高纯净度", ["DOMAIN-SUFFIX,openai.com"], ai),
        ("nsfw", "NSFW 大流量", ["DOMAIN-SUFFIX,missav.ws"], bulk),
        ("static", "Static 静态资源与下载", ["DOMAIN-SUFFIX,jsdelivr.net"], bulk),
        ("bulk", "大流量与开发站点", ["DOMAIN-SUFFIX,youtube.com"], bulk),
        ("china", "中国大陆与局域网", ["GEOSITE,cn", "GEOIP,CN,no-resolve"], None),
    ]
    legacy = {}
    for key, name, rules, group in originals:
        rule = RuleSet(
            name=name,
            template_key=key if tagged else None,
            rules_json=rules,
            target_mode="group" if group else "direct",
            target_group=group,
            sort_order=-103 if key == "bulk" else -100,
        )
        db.add(rule)
        legacy[key] = rule
    db.commit()
    return ai, bulk, legacy


@pytest.mark.parametrize("tagged", [True, False])
def test_legacy_rules_become_individual_categories_and_export(db, tagged):  # type: ignore[no-untyped-def]
    ai, bulk, legacy = seed_legacy(db, tagged)
    custom = RuleSet(
        name="My custom rule",
        rules_json=["DOMAIN,custom.example.com"],
        target_mode="reject",
        sort_order=-9999,
    )
    db.add(custom)
    db.commit()
    assert migrate_geosite_rules(db) is True
    rules = db.scalars(select(RuleSet)).all()
    categories = {rule.name: rule for rule in rules if rule.template_key}
    assert set(categories) == {
        "private",
        "cn",
        "category-ai-!cn",
        "category-porn",
        "category-cdn-!cn",
        "category-dev",
        "category-entertainment",
        "category-cryptocurrency",
        "category-ads-all",
    }
    assert len(rules) == 10
    assert categories["category-ai-!cn"].id == legacy["ai"].id
    assert categories["category-ai-!cn"].target_group == ai
    for code in ["category-porn", "category-cdn-!cn", "category-dev", "category-entertainment"]:
        assert categories[code].target_group == bulk
        assert categories[code].rules_json == [f"GEOSITE,{code}"]
    assert categories["category-cryptocurrency"].target_mode == "proxy"
    assert categories["category-cryptocurrency"].group_id is None
    assert categories["category-ads-all"].enabled is False
    assert custom.rules_json == ["DOMAIN,custom.example.com"]
    assert custom.target_mode == "reject"
    assert custom.sort_order == -9999
    backup = db.get(DataMigration, MIGRATION_ID).details_json
    assert len(backup["original_rules"]) == 5
    assert (
        next(row for row in backup["original_rules"] if row["id"] == legacy["bulk"].id)[
            "sort_order"
        ]
        == -103
    )
    assert ai.strategy == "url-test"
    assert bulk.strategy == "fallback"
    sub = Subscription(
        name="all", token_hash="test", token_hint="test", config_json={"group_name": "Main"}
    )
    db.add(sub)
    db.commit()
    generated = generate_clash(db, sub)
    document = yaml.safe_load(generated.content)
    assert generated.warnings == []
    assert document["rules"][0] == "DOMAIN,custom.example.com,REJECT"
    assert "GEOSITE,category-cryptocurrency,Main" in document["rules"]
    assert not any("category-ads-all" in rule for rule in document["rules"])
    assert document["rules"].index("GEOSITE,category-ai-!cn,AI") < document["rules"].index(
        "GEOSITE,category-dev,大流量"
    )
    assert document["rules"].index("GEOIP,private,DIRECT,no-resolve") < document["rules"].index(
        "GEOSITE,category-ai-!cn,AI"
    )
    assert document["rules"][-2:] == ["GEOIP,CN,DIRECT,no-resolve", "MATCH,Main"]


def test_conversion_does_not_override_later_edits_or_restore_deleted_categories(db):  # type: ignore[no-untyped-def]
    seed_legacy(db)
    assert migrate_geosite_rules(db)
    ai = db.scalar(select(RuleSet).where(RuleSet.name == "category-ai-!cn"))
    ai.rules_json = ["GEOSITE,openai"]
    ai.enabled = False
    ai.sort_order = 42
    db.delete(db.scalar(select(RuleSet).where(RuleSet.name == "category-ads-all")))
    db.commit()
    assert migrate_geosite_rules(db) is False
    assert ai.rules_json == ["GEOSITE,openai"]
    assert ai.enabled is False
    assert ai.sort_order == 42
    assert db.scalar(select(RuleSet).where(RuleSet.name == "category-ads-all")) is None


def test_missing_groups_defer_conversion_without_modifying_legacy_rules(db):  # type: ignore[no-untyped-def]
    _, _bulk, legacy = seed_legacy(db)
    ai_rule = legacy["ai"]
    ai_rule.target_group = None
    ai_rule.target_mode = "proxy"
    old_ai = db.scalar(select(Group).where(Group.name == "AI"))
    old_ai.name = "AI 日本"
    db.add(Group(name="AI 美国"))
    db.commit()
    assert migrate_geosite_rules(db) is False
    assert ai_rule.name == "AI 高纯净度"
    assert ai_rule.rules_json == ["DOMAIN-SUFFIX,openai.com"]
    assert db.get(DataMigration, MIGRATION_ID) is None
    ai_rule.target_group = old_ai
    ai_rule.target_mode = "group"
    db.commit()
    assert migrate_geosite_rules(db) is True


def test_custom_only_database_is_not_seeded_or_rewritten(db):  # type: ignore[no-untyped-def]
    custom = RuleSet(name="AI 高纯净度", target_mode="direct", rules_json=["GEOSITE,openai"])
    db.add(custom)
    db.commit()
    assert migrate_geosite_rules(db) is False
    assert db.scalars(select(RuleSet)).all() == [custom]
    assert custom.name == "AI 高纯净度"
    assert custom.rules_json == ["GEOSITE,openai"]


def test_database_startup_performs_conversion_only_once(db, monkeypatch):  # type: ignore[no-untyped-def]
    from sboard import database

    seed_legacy(db)
    monkeypatch.setattr(database, "engine", db.get_bind())
    database.init_db()
    assert db.get(DataMigration, MIGRATION_ID) is not None
    categories = db.scalars(select(RuleSet)).all()
    assert len(categories) == 9
    category_ids = {rule.id for rule in categories}
    database.init_db()
    assert {rule.id for rule in db.scalars(select(RuleSet)).all()} == category_ids


def test_proxy_target_api_uses_each_subscriptions_main_group(client, admin_headers):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/rules",
        headers=admin_headers,
        json={
            "name": "Crypto",
            "target_mode": "proxy",
            "rules": ["GEOSITE,category-cryptocurrency"],
        },
    )
    assert response.status_code == 201
    for invalid in [{"node_id": "invalid-node"}, {"group_id": "invalid-group"}]:
        rejected = client.patch(
            f"/api/v1/rules/{response.json()['id']}", headers=admin_headers, json=invalid
        )
        assert rejected.status_code == 422
    for name in ["Stable", "Main"]:
        sub = client.post(
            "/api/v1/subscriptions",
            headers=admin_headers,
            json={
                "name": name,
                "config": {"group_name": name},
            },
        ).json()["subscription"]
        exported = client.get(
            f"/api/v1/subscriptions/{sub['id']}/preview?format=clash", headers=admin_headers
        ).json()
        document = yaml.safe_load(exported["content"])
        assert document["rules"] == [
            f"GEOSITE,category-cryptocurrency,{name}",
            f"MATCH,{name}",
        ]
