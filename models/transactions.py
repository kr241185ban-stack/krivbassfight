from pydantic import BaseModel, Field
from typing import Optional

class PaymentModel(BaseModel):
    """Модель запису з листа 'Оплати'"""
    payment_id: str = Field(alias="Payment ID")
    athlete_id: str = Field(alias="Athlete ID")
    representative_id: str = Field(alias="Representative ID")
    group_id: Optional[str] = Field(None, alias="Group ID")
    
    period: str = Field(alias="Період")  # Напр. "Вересень 2026"
    amount: float = Field(alias="Сума")
    payment_date: Optional[str] = Field(None, alias="Дата оплати")
    
    status: str = Field(alias="Статус")  # 'Сплачено', 'В очікуванні'
    comment: Optional[str] = Field(None, alias="Коментар")

class ResultModel(BaseModel):
    """Модель запису з листа 'Результати'"""
    result_id: str = Field(alias="Result ID")
    competition_id: str = Field(alias="Competition ID")
    athlete_id: str = Field(alias="Athlete ID")
    
    discipline: str = Field(alias="Дисципліна") # Напр. "Куміте", "Ката"
    place: Optional[str] = Field(None, alias="Місце")
    result_score: Optional[str] = Field(None, alias="Результат")
    note: Optional[str] = Field(None, alias="Примітка")