from pydantic import BaseModel, Field
from typing import Optional

class CompetitionModel(BaseModel):
    competition_id: str = Field(alias="Competition ID")
    title: str = Field(alias="Назва")
    date: str = Field(alias="Дата")  # Формат: ДД.ММ.РРРР
    location: Optional[str] = Field(None, alias="Місце")
    status: Optional[str] = Field("заплановане", alias="Статус")
    note: Optional[str] = Field(None, alias="Примітка")