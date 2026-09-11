from pydantic import BaseModel, Field
from typing import Optional

class AttendanceModel(BaseModel):
    """Модель запису з листа 'Відвідування'"""
    attendance_id: str = Field(alias="Attendance ID")
    date: str = Field(alias="Дата")
    athlete_id: str = Field(alias="Athlete ID")
    group_id: str = Field(alias="Group ID")
    trainer_id: str = Field(alias="Trainer ID")
    
    status: str = Field(alias="Статус")  # 'Присутній', 'Відсутній', 'Хворів'
    comment: Optional[str] = Field(None, alias="Коментар")

class EvaluationModel(BaseModel):
    """Модель запису з листа 'Оцінювання'"""
    evaluation_id: str = Field(alias="Evaluation ID")
    date: str = Field(alias="Дата")
    athlete_id: str = Field(alias="Athlete ID")
    group_id: str = Field(alias="Group ID")
    trainer_id: str = Field(alias="Trainer ID")
    
    # Оцінки за тренування (від 1 до 5)
    behavior: Optional[int] = Field(None, alias="Поведінка")
    diligence: Optional[int] = Field(None, alias="Старанність")
    technique: Optional[int] = Field(None, alias="Техніка")
    
    # Загальна оцінка може містити кому (напр. "4,66"), тому краще прийняти як рядок (str)
    # або float, але тоді треба буде обробляти коми на рівні сервісу. Залишимо str для безпеки.
    total_score: Optional[str] = Field(None, alias="Загальна оцінка")
    comment: Optional[str] = Field(None, alias="Коментар")