"""
Стресс-тест: конфликт промпта и схемы в заявках на курсы ДПО.
---
Проверяем, при каком max_retries модель сдаётся, если промпт
говорит «придумай оригинальный курс», а схема разрешает только
фиксированный Literal[...].
"""

import time

from typing import Literal
from pydantic import BaseModel, Field
from llm_client import get_model, make_client

client = make_client()
MODEL = get_model()


# ───── Конфликт: промпт просит оригинальный курс, схема — только из списка ─────
FREE_COURSE_PROMPT = (
    "Сгенерируй заявку на курс повышения квалификации. "
    "ВАЖНО: в поле desired_course придумай оригинальное, творческое название курса. "
    "Не используй шаблонные названия — только уникальные авторские формулировки."
)


class ApplicationWithFixedCourse(BaseModel):
    full_name: str
    age: int = Field(ge=22, le=65)
    desired_course: Literal[
        "Управление проектами",
        "Цифровая трансформация бизнеса",
        "Охрана труда и промышленная безопасность",
        "Государственное и муниципальное управление",
        "Финансовый менеджмент и бюджетирование",
        "Педагогика и методика преподавания",
        "Медицинская статистика и аналитика",
        "Корпоративное право и договорная работа",
    ]


def stress(label: str, max_retries: int):
    print(f"\n--- {label} (max_retries={max_retries}) ---")
    t0 = time.time()
    try:
        obj = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": FREE_COURSE_PROMPT},
                {"role": "user", "content": "Создай одну заявку."},
            ],
            response_model=ApplicationWithFixedCourse,
            max_retries=max_retries,
            temperature=0.9,
        )
        dt = time.time() - t0
        print(f"Успех за {dt:.1f}с: {obj.full_name} — {obj.desired_course}")
    except Exception as e:
        dt = time.time() - t0
        print(f"Сдались за {dt:.1f}с, потрачено ~{max_retries + 1} запросов")
        print(f"{type(e).__name__}: {str(e)[:200]}")


def main():
    print(f"Модель: {MODEL}")
    print("Конфликт: промпт требует оригинальный курс, схема — только Literal[...]")

    stress("max_retries=0", max_retries=0)
    stress("max_retries=1", max_retries=1)
    stress("max_retries=3", max_retries=3)
    stress("max_retries=5", max_retries=5)

    print("\n--- Вывод ---")
    print("Если модель читает JSON Schema из системного промпта — она выбирает схему.")
    print("Если следует тексту промпта — выдаёт свободный курс и валится.")
    print("Retry не решает конфликт, только тратит токены.")


if __name__ == "__main__":
    main()