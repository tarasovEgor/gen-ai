from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


CITIES = [
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург",
    "Казань", "Нижний Новгород", "Самара", "Краснодар", "Сочи", "Владивосток"
]


class Address(BaseModel):
    city: str
    district: str = Field(min_length=2, max_length=40)

    @field_validator("city")
    @classmethod
    def city_must_be_in_list(cls, v: str) -> str:
        if v not in CITIES:
            raise ValueError(f"Город «{v}» не из утверждённого списка")
        return v
    

class Application(BaseModel):
    full_name: str
    age: int = Field(ge=22, le=65)
    address: Address
    speciality: Literal[
        "студент", "инженер", "менеджер", "учитель",
        "врач", "предприниматель", "пенсионер", "IT-специалист",
    ]
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
    years_of_experience: int = Field(ge=0, le=40)
    graduation_year: int = Field(ge=1980, le=2024)

    @field_validator("graduation_year")
    @classmethod
    def graduation_year_in_range(cls, v: int) -> int:
        current_year = datetime.now().year
        if v < 1970 or v > current_year:
            raise ValueError(f"graduation_year должен быть от 1970 до {current_year}")
        return v