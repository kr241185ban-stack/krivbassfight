from pydantic import BaseModel, Field, field_validator
from typing import Optional

class AthleteModel(BaseModel):
    athlete_id: str = Field(alias="Athlete ID")
    full_name: str = Field(alias="ПІБ")
    birth_date: Optional[str] = Field(None, alias="Дата народження")
    gender: Optional[str] = Field(None, alias="Стать")
    
    belt: Optional[str] = Field(None, alias="POYAS")          # '14 кю', '1 дан' і т.д.
    rank: Optional[str] = Field(None, alias="KMS MS")         # 'Юнацький', 'КМС', 'МС'
    weight: Optional[float] = Field(None, alias="VAGA")       # Вага в кг
    
    school_id: str = Field(alias="School ID")
    group_id: Optional[str] = Field(None, alias="Group ID")
    trainer_id: str = Field(alias="Trainer ID")
    representative_id: Optional[str] = Field(None, alias="Representative ID")
    
    status: str = Field(alias="Статус")

    @field_validator('weight', mode='before')
    @classmethod
    def parse_weight(cls, v):
        """Безпечно конвертує порожні рядки або значення з комами у float або None"""
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            v = v.replace(',', '.').strip()
            if not v:
                return None
        try:
            return float(v)
        except ValueError:
            return None