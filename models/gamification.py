from pydantic import BaseModel, Field
from typing import Optional

class TaskModel(BaseModel):
    """Модель з аркуша 'Опис завдання' (довідник)"""
    progress_id: str = Field(alias="Progress ID")
    date: Optional[str] = Field(None, alias="Дата")
    name: str = Field(alias="NAME ZAVDAN")
    description: Optional[str] = Field(None, alias="OPUS ZAVDAN")
    target_value: Optional[str] = Field(None, alias="Показник")
    unit: Optional[str] = Field(None, alias="Одиниця виміру")
    sticker_id: str = Field(alias="STIKER ID")

class AchievementModel(BaseModel):
    """Нормалізована модель з аркуша 'Досягнення' (без дублювання полів)"""
    achievement_id: str = Field(alias="Achievement ID")
    athlete_id: str = Field(alias="Athlete ID")
    progress_id: str = Field(alias="Progress ID")
    completion_date: Optional[str] = Field(None, alias="Дата виконання")
    current_value: Optional[str] = Field("0", alias="Значення виконання")
    status: str = Field(alias="STATUS VIKONAN")  # 'Нове', 'В очікуванні', 'Виконано'