# Файл: api/routers/gamification.py
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from api.dependencies import get_current_user
from models.user import UserModel
from services.sheets_client import sheets_service

router = APIRouter()

# --- Схеми для вхідних даних (Requests) ---
class SubmitAchievement(BaseModel):
    athlete_id: str
    task_id: str             # Збігається з "Progress ID" / "ZAVDANYAID"
    task_name: str           # Назва нормативу
    achieved_value: float    # Скільки по факту зробив спортсмен
    target_value: float      # Скільки вимагалося
    unit: str                # Одиниця виміру (рази, кг, хв)
    sticker_id: str          # Посилання на стікер у Google Drive

class VerifyAchievement(BaseModel):
    achievement_id: str
    new_status: str          # 'Зараховано' або 'Відхилено'

# --- Маршрути (Endpoints) ---

@router.get("/tasks")
async def get_tasks(user: UserModel = Depends(get_current_user)):
    """Каталог доступних нормативів (доступно всім ролям)"""
    tasks = sheets_service.get_all_tasks()
    if not tasks:
        raise HTTPException(status_code=404, detail="Завдань не знайдено.")
    return tasks

@router.get("/achievements/{athlete_id}")
async def get_achievements(athlete_id: str, user: UserModel = Depends(get_current_user)):
    """Отримати колекцію стікерів (досягнень) конкретного спортсмена"""
    achievements = sheets_service.get_athlete_achievements(athlete_id)
    return achievements

@router.post("/achievements/submit")
async def submit_achievement(payload: SubmitAchievement, user: UserModel = Depends(get_current_user)):
    """Подача заявки на виконання завдання (Спортсмен або Тренер)"""
    achievement_id = f"ACH-{uuid.uuid4().hex[:8].upper()}"
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    # Порядок колонок згідно з базою "Досягнення": 
    # Achievement ID | Athlete ID | Дата виконання | Progress ID | NAME ZAVDAN | Значення | Показник | Одиниця | STATUS VIKONAN | STIKER ID
    row = [
        achievement_id,
        payload.athlete_id,
        current_date,
        payload.task_id,
        payload.task_name,
        payload.achieved_value,
        payload.target_value,
        payload.unit,
        "В очікуванні",      # Завжди дефолтний статус при подачі
        payload.sticker_id
    ]
    
    try:
        sheets_service.append_achievement(row)
        return {"status": "success", "message": "Заявку відправлено на перевірку тренеру."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка бази даних: {str(e)}")

@router.put("/achievements/verify")
async def verify_achievement(payload: VerifyAchievement, user: UserModel = Depends(get_current_user)):
    """Верифікація (перевірка) завдання тренером"""
    if user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Тільки тренер або адміністратор може верифікувати завдання.")
        
    success = sheets_service.verify_achievement(payload.achievement_id, payload.new_status)
    
    if success:
        return {"status": "success", "message": f"Статус змінено на '{payload.new_status}'"}
    else:
        raise HTTPException(status_code=404, detail="Заявку не знайдено в базі.")