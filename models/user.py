from pydantic import BaseModel
from typing import Optional

class UserModel(BaseModel):
    user_id: str
    telegram_id: int
    role: str  # 'admin', 'trainer', 'representative', 'athlete'
    representative_id: Optional[str] = None
    athlete_id: Optional[str] = None
    trainer_id: Optional[str] = None
    status: str  # 'Активний', 'Очікує', 'Заблокований'