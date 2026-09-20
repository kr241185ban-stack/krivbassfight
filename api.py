from typing import Optional
import json
import asyncio
from urllib.parse import parse_qsl
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from services.auth_service import auth_service
from database.sheets_repository import sheets_repo, normalize_id
from models.training import AttendanceModel, EvaluationModel
import uuid
from models.transactions import PaymentModel
from models.gamification import AchievementModel
import datetime
import os
import html
import requests
from config import config  # Отримуємо налаштування з config.py

TRAINER_CHAT_ID = os.getenv("TRAINER_CHAT_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI(title="KrivbassFight CRM API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")

class RemindRequest(BaseModel):
    athlete_id: str
    period: str

def extract_telegram_id(init_data: str) -> int:
    try:
        parsed = dict(parse_qsl(init_data))
        user_json = parsed.get("user")
        if user_json:
            user_data = json.loads(user_json)
            return int(user_data["id"])
    except Exception as e:
        print(f"Помилка парсингу initData: {e}")
    return None

@app.get("/api/v1/me")
async def api_get_my_profile(
    athlete_id: Optional[str] = None,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    telegram_id = None

    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    
    if not telegram_id and x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Відсутні або некоректні дані ідентифікації")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    
    if not user or str(user.status).strip().lower() != "активний":
        raise HTTPException(status_code=403, detail="Доступ заборонено або акаунт неактивний")

    name = "Користувач"
    group_name = "Основна"
    trainer_name = "Адміністрація"
    kil_stiker = "0"

    target_athlete_id = athlete_id or user.athlete_id

    if target_athlete_id:
        athlete = sheets_repo.get_athlete_by_id(target_athlete_id)
        if athlete:
            name = athlete.full_name
            group_name = sheets_repo.get_group_name_by_id(athlete.group_id)
            trainer_name = sheets_repo.get_trainer_name_by_id(athlete.trainer_id)
            kil_stiker = sheets_repo.get_athlete_sticker_count(target_athlete_id)
    elif user.role == "admin":
        name = "Адміністратор"
        group_name = "Всі групи"
        trainer_name = "Головний тренер"
    elif user.role == "trainer":
        name = "Тренер"
        group_name = "Тренерський склад"
        trainer_name = "Самостійно"

    return {
        "status": "success",
        "telegram_id": telegram_id,
        "role": user.role,
        "name": name,
        "group_name": group_name,
        "trainer_name": trainer_name,
        "athlete_id": target_athlete_id,
        "trainer_id": user.trainer_id,
        "representative_id": user.representative_id,
        "kil_stiker": kil_stiker
    }

@app.post("/api/v1/attendance")
async def api_mark_attendance(
    data: AttendanceModel,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Ендпоінт для тренера/адміна: збереження відвідуваності"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для редагування")

    try:
        sheets_repo.update_attendance(
            attendance_id=data.attendance_id or str(uuid.uuid4())[:8],
            date=data.date,
            athlete_id=data.athlete_id,
            group_id=data.group_id,
            trainer_id=data.trainer_id,
            status=data.status,
            comment=data.comment or ""
        )
        return {"status": "success", "message": "Відвідуваність успішно збережено"}
    except Exception as e:
        print(f"Помилка запису відвідуваності: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при збереженні")

@app.post("/api/v1/evaluations")
async def api_save_evaluation(
    data: EvaluationModel,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Ендпоінт для тренера/адміна: збереження оцінок спортсмена"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для виставлення оцінок")

    try:
        b = data.behavior or 5
        d = data.diligence or 5
        t = data.technique or 5
        avg = round((b + d + t) / 3, 2)
        total_str = str(avg).replace('.', ',')

        sheets_repo.update_evaluation(
            evaluation_id=data.evaluation_id or str(uuid.uuid4())[:8],
            date=data.date,
            athlete_id=data.athlete_id,
            group_id=data.group_id,
            trainer_id=data.trainer_id,
            behavior=b,
            diligence=d,
            technique=t,
            total_score=total_str,
            comment=data.comment or ""
        )
        return {"status": "success", "message": "Оцінки успішно збережено", "total_score": total_str}
    except Exception as e:
        print(f"Помилка запису оцінки: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при збереженні оцінки")

@app.get("/api/v1/payments")
async def api_get_payments(
    athlete_id: Optional[str] = None,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання історії оплат та перевірка статусу за поточний місяць"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if user.role in ["admin", "trainer"]:
        target_athlete_id = athlete_id or user.athlete_id or "ATH-0007"

    payments = sheets_repo.get_payments_by_athlete(target_athlete_id) if target_athlete_id else []

    now = datetime.date.today()
    months_uk = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
    current_period = f"{months_uk[now.month - 1]} {now.year}".lower()

    is_paid_current_month = False
    for p in payments:
        period_str = str(p.get("Період") or p.get("period") or "").strip().lower()
        status_str = str(p.get("Статус") or p.get("status") or "").strip().lower()
        if current_period in period_str and status_str in ["сплачено", "paid"]:
            is_paid_current_month = True
            break

    return {
        "status": "success",
        "payments": payments,
        "is_paid_current_month": is_paid_current_month,
        "current_period": current_period
    }

@app.post("/api/v1/payments")
async def api_add_payment(
    data: dict,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Збереження нової оплати тренером/адміном у Google Таблицю"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для внесення оплат")

    athlete_id = data.get("athlete_id")
    period = data.get("period")
    amount = data.get("amount")

    if not athlete_id or not period or not amount:
        raise HTTPException(status_code=400, detail="Заповніть усі обов'язкові поля (спортсмен, період, сума)")

    try:
        today_str = datetime.date.today().strftime("%d.%m.%Y")
        payment_id = f"PAY-{uuid.uuid4().hex[:6].upper()}"

        athlete = sheets_repo.get_athlete_by_id(athlete_id)
        rep_id = athlete.representative_id if athlete else ""
        grp_id = athlete.group_id if athlete else ""

        sheets_repo.upsert_payment(
            payment_id=payment_id,
            athlete_id=athlete_id,
            representative_id=rep_id,
            group_id=grp_id,
            period=period,
            amount=str(amount),
            payment_date=today_str,
            status="Сплачено",
            comment=""
        )
        return {"status": "success", "message": "Оплату успішно збережено!"}
    except Exception as e:
        print(f"Помилка додавання оплати: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при збереженні оплати")

@app.get("/api/v1/payments/status")
async def api_get_payments_status(
    group_id: str = Query(..., description="Group ID або назва групи"),
    period: str = Query(..., description="Період у форматі ММ.РРРР (наприклад: 09.2026)"),
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання зведеного статусу оплат для тренера по конкретній групі за вибраний період"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для перегляду оплат")

    data = await asyncio.to_thread(sheets_repo.get_group_payments_status, group_id, period)
    return {"status": "success", **data}

@app.post("/api/v1/payments/remind")
async def api_send_payment_reminder(
    payload: RemindRequest,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Відправка персонального нагадування про оплату в Telegram родичу або спортсмену"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для відправки нагадувань")

    users = await asyncio.to_thread(sheets_repo._get_cached_records, "Користувачі")
    target_tg_id = None

    norm_target_ath = normalize_id(payload.athlete_id)
    for u in users:
        u_ath = normalize_id(str(u.get("Athlete ID") or u.get("athlete_id") or ""))
        u_status = str(u.get("Статус") or u.get("status") or "").strip().lower()

        if u_ath == norm_target_ath and u_status == "активний":
            raw_tg = str(u.get("Telegram ID") or u.get("telegram_id") or "").strip().split('.')[0]
            if raw_tg.isdigit():
                target_tg_id = int(raw_tg)
                break

    if not target_tg_id:
        raise HTTPException(status_code=404, detail="Telegram ID для даного спортсмена не знайдено")

    msg = (
        f"🔔 <b>Нагадування про оплату</b>\n\n"
        f"Шановний користувач, будь ласка, не забудьте внести оплату за абонемент "
        f"за період <b>{payload.period}</b>.\n\n"
        f"<i>З повагою, тренерський склад СК «Рукопашник».</i>"
    )

    bot_token = config.bot_token
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload_tg = {
        "chat_id": target_tg_id,
        "text": msg,
        "parse_mode": "HTML"
    }

    try:
        res = await asyncio.to_thread(requests.post, url, json=payload_tg, timeout=5)
        if res.status_code == 200:
            return {"status": "success", "message": "Нагадування успішно надіслано"}
        else:
            raise HTTPException(status_code=500, detail=f"Помилка Telegram API ({res.status_code})")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка відправки: {e}")

@app.get("/api/v1/tasks")
async def api_get_tasks(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Відображає тільки АКТИВНІ (LIFE='Активне') та НЕВИКОНАНИХ завдання"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if not target_athlete_id and user.role in ["admin", "trainer"]:
        target_athlete_id = "ATH-01"

    all_tasks = sheets_repo.get_tasks_for_athlete(target_athlete_id) if target_athlete_id else []
    
    active_uncompleted_tasks = [
        t for t in all_tasks
        if str(t.get("LIFE", "")).strip().lower() == "активне"
        and str(t.get("STATUS VIKONAN", "")).strip().lower() not in ["виконан", "виконано", "зараховано"]
    ]
    
    return {"status": "success", "tasks": active_uncompleted_tasks}

@app.post("/api/v1/tasks/update")
async def api_update_task(
    data: dict,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Оновлення статусу виконання завдання тренером/адміном"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав")

    try:
        today = datetime.date.today().strftime("%d.%m.%Y")
        
        sheets_repo.upsert_achievement(
            achievement_id=data.get("achievement_id", ""),
            athlete_id=data.get("athlete_id", "ATH-01"),
            progress_id=data.get("progress_id"),
            date=data.get("date", today),
            current_value=str(data.get("current_value", "100")),
            status=data.get("status", "Виконано")
        )
        return {"status": "success", "message": "Статус завдання успішно оновлено!"}
    except Exception as e:
        print(f"Помилка оновлення завдання: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при оновленні")

@app.get("/api/v1/competitions")
async def api_get_competitions(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання списку змагань із Google Таблиці"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    competitions = sheets_repo.get_competitions()
    return {"status": "success", "competitions": competitions}

@app.get("/api/v1/schedule")
async def api_get_schedule(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання персонального розкладу спортсмена за його Group ID"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_group_id = None
    if user.athlete_id:
        athlete = sheets_repo.get_athlete_by_id(user.athlete_id)
        if athlete:
            target_group_id = athlete.group_id

    schedule = sheets_repo.get_schedule_for_athlete_group(target_group_id)
    return {"status": "success", "schedule": schedule}

@app.get("/api/v1/achievements")
async def api_get_achievements(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Відображає стікери тільки за завдання зі статусом 'виконан'"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if not target_athlete_id and user.role in ["admin", "trainer"]:
        target_athlete_id = "ATH-01"

    all_tasks = sheets_repo.get_tasks_for_athlete(target_athlete_id) if target_athlete_id else []

    unlocked_achievements = [
        t for t in all_tasks
        if str(t.get("STATUS VIKONAN", "")).strip().lower() in ["виконан", "виконано", "зараховано"]
    ]
    
    return {"status": "success", "achievements": unlocked_achievements}

@app.get("/api/v1/results")
async def api_get_results(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання персональної статистики та історії результатів спортсмена"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if not target_athlete_id and user.role in ["admin", "trainer"]:
        target_athlete_id = "ATH-0007"

    data = sheets_repo.get_athlete_results_data(target_athlete_id) if target_athlete_id else {"stats": {}, "history": []}
    return {"status": "success", "results": data}

@app.get("/api/v1/evaluations")
async def api_get_evaluations(
    athlete_id: Optional[str] = None,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання списку оцінок поточного або обраного тренером/адміном спортсмена"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if user.role in ["admin", "trainer"]:
        target_athlete_id = athlete_id or user.athlete_id or "ATH-0007"

    data = sheets_repo.get_evaluations_data(target_athlete_id) if target_athlete_id else {"summary": {}, "daily": [], "monthly": []}
    return {"status": "success", "evaluations": data}

@app.get("/api/v1/attendance/athletes")
async def api_get_attendance_athletes(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Повертає список спортсменів для випадаючого списку тренера/адміна"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        return {"status": "success", "athletes": []}

    records = sheets_repo._get_cached_records("Спортсмени")
    athletes = []
    
    for r in records:
        tr_id = str(r.get("Trainer ID") or "").strip()
        if user.role == "admin" or (user.role == "trainer" and normalize_id(tr_id) == normalize_id(user.trainer_id)):
            athletes.append({
                "athlete_id": str(r.get("Athlete ID") or "").strip(),
                "full_name": str(r.get("ПІБ") or "").strip()
            })

    return {"status": "success", "athletes": athletes}

@app.get("/api/v1/attendance")
async def api_get_attendance(
    athlete_id: Optional[str] = None,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання статистики відвідуваності поточного або обраного тренером спортсмена"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if user.role in ["admin", "trainer"]:
        target_athlete_id = athlete_id or user.athlete_id or "ATH-0007"

    data = sheets_repo.get_attendance_data(target_athlete_id) if target_athlete_id else {"stats": {}, "history": []}
    return {"status": "success", "attendance": data}

@app.get("/api/v1/my-groups")
async def api_get_my_groups(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання списку груп для тренера або адміна"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Доступ заборонено")

    groups = sheets_repo.get_groups_for_user(user.role, user.trainer_id)
    return {"status": "success", "groups": groups}

@app.get("/api/v1/my-groups/{group_id}/athletes")
async def api_get_group_athletes(
    group_id: str,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання списку спортсменів конкретної групи"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Доступ заборонено")

    athletes = sheets_repo.get_athletes_by_group(group_id)
    return {"status": "success", "athletes": athletes}

@app.post("/api/v1/my-groups/submit")
async def api_submit_group_data(
    data: dict,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Пакетне збереження відвідуваності та оцінок групи"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and x_telegram_id.isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав")

    group_id = data.get("group_id")
    items = data.get("items", [])

    if not group_id or not items:
        raise HTTPException(status_code=400, detail="Відсутні дані для збереження")

    try:
        sheets_repo.bulk_save_group_data(group_id, items)
        return {"status": "success", "message": "Дані успішно передано та збережено!"}
    except Exception as e:
        print(f"Помилка при збереженні групи: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при записі в Google Таблицю")

@app.get("/api/v1/profile")
async def api_get_profile(
    athlete_id: Optional[str] = None,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Отримання розширених даних профілю"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    target_athlete_id = user.athlete_id
    if user.role in ["admin", "trainer"]:
        target_athlete_id = athlete_id or user.athlete_id or "ATH-0007"

    profile_data = sheets_repo.get_athlete_profile_details(target_athlete_id)
    
    groups = sheets_repo.get_groups_for_user(user.role, user.trainer_id) if user.role in ["admin", "trainer"] else []

    return {
        "status": "success",
        "profile": profile_data,
        "available_groups": groups
    }

@app.post("/api/v1/profile/update")
async def api_update_profile(
    data: dict,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Оновлення ваги та групи тренером/адміном"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user or user.role not in ["admin", "trainer"]:
        raise HTTPException(status_code=403, detail="Недостатньо прав для редагування профілю")

    target_ath_id = data.get("athlete_id")
    vaga = data.get("vaga")
    group_id = data.get("group_id")

    if not target_ath_id:
        raise HTTPException(status_code=400, detail="Не вказано athlete_id")

    try:
        sheets_repo.update_athlete_profile_data(
            athlete_id=target_ath_id,
            vaga=vaga,
            group_id=group_id
        )
        return {"status": "success", "message": "Профіль успішно оновлено!"}
    except Exception as e:
        print(f"Помилка оновлення профілю: {e}")
        raise HTTPException(status_code=500, detail="Помилка сервера при оновленні профілю")

@app.post("/api/v1/messages")
async def api_send_message_to_trainers(
    data: dict,
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Надійна відправка повідомлення в чат тренерів через HTML-форматування"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    raw_text = str(data.get("text", "")).strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Текст повідомлення порожній")

    sender_name = "Спортсмен"
    group_name = "Основна"

    if user.athlete_id:
        profile = sheets_repo.get_athlete_profile_details(user.athlete_id)
        sender_name = profile.get("full_name", "Спортсмен")
        group_name = profile.get("group_name", "Основна")

    safe_text = html.escape(raw_text)
    safe_sender = html.escape(sender_name)
    safe_group = html.escape(group_name)
    safe_ath_id = html.escape(user.athlete_id or "-")

    msg_text = (
        f"📩 <b>Нове повідомлення з Mini App!</b>\n\n"
        f"👤 <b>Від кого:</b> {safe_sender}\n"
        f"♧ <b>Група:</b> {safe_group}\n"
        f"🆔 <b>Athlete ID:</b> <code>{safe_ath_id}</code>\n"
        f"📱 <b>TG ID:</b> <code>{telegram_id}</code>\n\n"
        f"💬 <b>Текст:</b>\n{safe_text}\n\n"
        f"<i>💡 Щоб відповісти спортсмену, зробіть Reply (Відповісти) на це повідомлення.</i>"
    )

    bot_token = config.bot_token
    chat_id = config.trainer_chat_id

    if not chat_id:
        print("Помилка: TRAINER_CHAT_ID не вказано у файлі .env")
        raise HTTPException(status_code=500, detail="Чат тренерів не налаштовано в конфігурації")

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload, timeout=5)
        
        if res.status_code != 200:
            print(f"Помилка Telegram API ({res.status_code}): {res.text}")
            raise HTTPException(status_code=500, detail="Telegram API відхилив повідомлення")

    except Exception as e:
        print(f"Не вдалося надіслати повідомлення в Telegram: {e}")
        raise HTTPException(status_code=500, detail="Помилка з'єднання з Telegram API")

    return {"status": "success", "message": "Повідомлення успішно надіслано тренерам!"}

@app.get("/api/v1/my-athletes")
async def api_get_my_athletes(
    x_telegram_init_data: str = Header(None),
    x_telegram_id: str = Header(None)
):
    """Повертає список дітей, прив'язаних до представника"""
    telegram_id = None
    if x_telegram_init_data:
        telegram_id = extract_telegram_id(x_telegram_init_data)
    elif x_telegram_id and str(x_telegram_id).isdigit():
        telegram_id = int(x_telegram_id)

    if not telegram_id:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    user = auth_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Користувача не знайдено")

    if user.role == "athlete":
        athlete = sheets_repo.get_athlete_by_id(user.athlete_id)
        return {"status": "success", "athletes": [{"athlete_id": user.athlete_id, "full_name": athlete.full_name if athlete else "Спортсмен"}]}

    records = sheets_repo._get_cached_records("Спортсмени")
    my_athletes = []
    
    for r in records:
        if str(r.get("Representative ID") or "").strip() == str(user.representative_id or "").strip():
            my_athletes.append({
                "athlete_id": str(r.get("Athlete ID") or "").strip(),
                "full_name": str(r.get("ПІБ") or "").strip()
            })

    return {"status": "success", "athletes": my_athletes}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
