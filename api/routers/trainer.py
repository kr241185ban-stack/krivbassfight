# Файл: api/routers/trainer.py
import uuid
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from api.dependencies import get_current_user
from models.user import UserModel
from services.sheets_client import sheets_service

router = APIRouter()

# --- Схеми для вхідних даних (Requests) ---
class AttendanceItem(BaseModel):
    athlete_id: str
    group_id: str
    status: str  # 'Присутній', 'Відсутній', 'Хворів'
    comment: Optional[str] = ""

class AttendancePayload(BaseModel):
    date: str  # Формат: 'DD.MM.YYYY'
    records: List[AttendanceItem]

class EvaluationItem(BaseModel):
    athlete_id: str
    group_id: str
    behavior: int       # Поведінка
    diligence: int      # Старанність
    technique: int      # Техніка
    total_score: str    # Загальна оцінка (напр. "4.66")
    comment: Optional[str] = ""

class EvaluationPayload(BaseModel):
    date: str  # Формат: 'DD.MM.YYYY'
    records: List[EvaluationItem]

# --- Маршрути (Endpoints) ---

@router.get("/groups")
async def get_my_groups(user: UserModel = Depends(get_current_user)):
    """Отримати групи. Адмін бачить усі, Тренер — тільки свої."""
    if user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    groups = sheets_service.get_trainer_groups(user.trainer_id)
    if not groups:
        raise HTTPException(status_code=404, detail="Групи не знайдено.")
    return groups

@router.get("/groups/{group_id}/athletes")
async def get_athletes_in_group(group_id: str, user: UserModel = Depends(get_current_user)):
    """Отримати список активних спортсменів у конкретній групі"""
    if user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    athletes = sheets_service.get_athletes_by_group(group_id)
    if not athletes:
        raise HTTPException(status_code=404, detail="Спортсменів не знайдено.")
    return athletes

@router.post("/attendance")
async def mark_attendance(payload: AttendancePayload, user: UserModel = Depends(get_current_user)):
    """Пакетне збереження відвідуваності всієї групи"""
    if user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    rows_to_add = []
    
    # Перетворюємо JSON з фронтенду на масив рядків для Google Таблиці
    for record in payload.records:
        # Генеруємо унікальний ID для кожної відмітки (напр. ATT-4F8A...)
        attendance_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        
        row = [
            attendance_id,       # Attendance ID
            payload.date,        # Дата
            record.athlete_id,   # Athlete ID
            record.group_id,     # Group ID
            user.trainer_id,     # Trainer ID
            record.status,       # Статус
            record.comment       # Коментар
        ]
        rows_to_add.append(row)

    # Відправляємо весь пакет в Google Sheets одним запитом!
    try:
        sheets_service.batch_append_attendance(rows_to_add)
        return {"status": "success", "message": f"Збережено {len(rows_to_add)} відміток."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису в БД: {str(e)}")

@router.post("/evaluations")
async def save_evaluations(payload: EvaluationPayload, user: UserModel = Depends(get_current_user)):
    """Пакетне збереження оцінок спортсменів"""
    if user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    rows_to_add = []
    
    for record in payload.records:
        # Генеруємо унікальний ID для кожної оцінки
        eval_id = f"EVL-{uuid.uuid4().hex[:8].upper()}"
        
        # Порядок колонок ПОВИНЕН точно збігатися з листом "Оцінювання":
        row = [
            eval_id,             # Evaluation ID
            payload.date,        # Дата
            record.athlete_id,   # Athlete ID
            record.group_id,     # Group ID
            user.trainer_id,     # Trainer ID
            record.behavior,     # Поведінка
            record.diligence,    # Старанність
            record.technique,    # Техніка
            record.total_score,  # Загальна оцінка
            record.comment       # Коментар
        ]
        rows_to_add.append(row)

    try:
        sheets_service.batch_append_evaluations(rows_to_add)
        return {"status": "success", "message": f"Збережено {len(rows_to_add)} оцінок."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка запису оцінок в БД: {str(e)}")