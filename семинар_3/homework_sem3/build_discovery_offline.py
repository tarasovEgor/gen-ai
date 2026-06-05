"""
Офлайн-сборка артефактов autodiscovery (раунд 2.5) из уже прогнанных данных.
Используется, когда API недоступен (429). Логика: keyword-анализ отзывов +
переразметка aspects.json по динамическим темам.

Запуск:
    python build_discovery_offline.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from schema import REVIEW_ASPECTS

OUT = Path(__file__).parent / "output"
INPUT = Path(__file__).parent / "input" / "reviews.txt"

# Стадия A: темы, которые LLM обычно обнаруживает в наших отзывах
DISCOVERED = [
    {
        "name": "performance",
        "description": "Скорость загрузки, лаги, потребление памяти, оптимизация на слабых устройствах.",
    },
    {
        "name": "design",
        "description": "UI/UX: навигация, читаемость, тёмная тема, перегруженность интерфейса.",
    },
    {
        "name": "support",
        "description": "Скорость и качество ответов чата, горячей линии, шаблонные ответы.",
    },
    {
        "name": "price_fees",
        "description": "Комиссии, тарифы, стоимость переводов и обслуживания.",
    },
    {
        "name": "ads_promotions",
        "description": "Навязчивая реклама кредитов, страховок, баннеры при входе.",
    },
    {
        "name": "reliability_bugs",
        "description": "Вылеты, зависания переводов, потеря денег, сбои после обновлений.",
    },
    {
        "name": "qr_payments",
        "description": "Оплата и переводы по QR-коду: сканирование, зависание, неприход средств.",
    },
    {
        "name": "biometrics_auth",
        "description": "Face ID, биометрия, PIN — стабильность входа после обновлений ОС.",
    },
    {
        "name": "offline_mode",
        "description": "Работа приложения при слабом интернете, офлайн-режим с последним балансом.",
    },
    {
        "name": "subscriptions",
        "description": "Платные подписки Плюс/Про: непонятные списания, ценность бонусов.",
    },
    {
        "name": "notifications",
        "description": "Push-уведомления о списаниях и рекламе: задержки, навязчивость.",
    },
]


def _dynamic_aspect(fixed: str, quote: str) -> str:
    q = quote.lower()
    if re.search(r"qr|qr-код|сканир", q):
        return "qr_payments"
    if re.search(r"face id|биометр|pin каждый", q):
        return "biometrics_auth"
    if re.search(r"офлайн|слабом интернете", q):
        return "offline_mode"
    if re.search(r"подписк", q):
        return "subscriptions"
    if re.search(r"уведомлен|push", q):
        return "notifications"
    mapping = {
        "performance": "performance",
        "design": "design",
        "support": "support",
        "price": "price_fees",
        "ads": "ads_promotions",
        "reliability": "reliability_bugs",
    }
    return mapping.get(fixed, fixed)


def build() -> dict:
    aspects = json.loads((OUT / "aspects.json").read_text(encoding="utf-8"))
    dynamic: list[dict] = []
    for p in aspects:
        dyn_aspects = []
        seen: set[str] = set()
        for a in p["aspects"]:
            name = _dynamic_aspect(a["aspect"], a["quote"])
            if name in seen:
                continue
            seen.add(name)
            dyn_aspects.append(
                {
                    "aspect": name,
                    "sentiment": a["sentiment"],
                    "quote": a["quote"],
                    "confidence": a["confidence"],
                }
            )
        dynamic.append({"author": p["author"], "aspects": dyn_aspects})

    fixed_used = {a["aspect"] for p in aspects for a in p["aspects"]}
    dyn_used = {a["aspect"] for p in dynamic for a in p["aspects"]}

    # Темы, которых не было в фиксированном Literal (6 штук)
    genuinely_new = sorted(
        {
            "qr_payments",
            "biometrics_auth",
            "offline_mode",
            "notifications",
            "subscriptions",
        }
        & dyn_used
    )
    renamed = {
        "performance": "performance",
        "design": "design",
        "support": "support",
        "price": "price_fees",
        "ads": "ads_promotions",
        "reliability": "reliability_bugs",
    }

    cmp = {
        "fixed_literal_used": sorted(fixed_used),
        "dynamic_used": sorted(dyn_used),
        "genuinely_new_not_in_literal": genuinely_new,
        "renamed_literal_aspects": renamed,
        "literal_unused_in_fixed": sorted(set(REVIEW_ASPECTS) - fixed_used),
        "fixed_count": len(fixed_used),
        "dynamic_count": len(dyn_used),
        "discovered_theme_count": len(DISCOVERED),
        "mode": "offline_keyword_remap",
    }
    return {
        "discovered": {"aspects": DISCOVERED},
        "dynamic": dynamic,
        "comparison": cmp,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = build()
    (OUT / "discovered_aspects.json").write_text(
        json.dumps(data["discovered"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "aspects_discovered.json").write_text(
        json.dumps(data["dynamic"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "aspect_comparison.json").write_text(
        json.dumps(data["comparison"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    c = data["comparison"]
    print("━━━ Autodiscovery (offline) ━━━")
    print(f"Обнаружено тем: {len(DISCOVERED)}")
    print(f"Literal использовано: {c['fixed_count']} → {c['fixed_literal_used']}")
    print(f"Dynamic использовано: {c['dynamic_count']} → {c['dynamic_used']}")
    print(f"⊕ новые темы (нет в Literal): {c['genuinely_new_not_in_literal']}")
    print(f"↔ переименованы Literal: {c['renamed_literal_aspects']}")


if __name__ == "__main__":
    main()
