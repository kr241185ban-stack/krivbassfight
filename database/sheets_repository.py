from __future__ import annotations

import asyncio
# інші ваші імпорти...
from typing import Optional
import os
import re
import uuid
import time
import datetime
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from models.user import UserModel
from models.athlete import AthleteModel

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def normalize_id(id_str: str) -> str:
    """Точно відокремлює букви від нулів, зберігаючи правильний номер (наприклад, ATH-0007 -> ath7, ATH-0030 -> ath30)"""
    if not id_str:
        return ""
    match = re.match(r'^([a-zA-Z]+)[-_]?0*(\d+)$', str(id_str).strip())
    if match:
        prefix, number = match.groups()
        return f"{prefix.lower()}{int(number)}"
    return str(id_str).strip().lower()

class SheetsRepository:
    def __init__(self):
        self.creds_file = "credentials.json"
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID")
        self._spreadsheet = None
        self._cache = {}
        self._default_ttl = 30  # Час життя кешу в секундах

    def _connect(self):
        """Підключення до Google Sheets із захистом від тимчасових помилок 500"""
        if not self._spreadsheet:
            creds = Credentials.from_service_account_file(self.creds_file, scopes=SCOPES)
            client = gspread.authorize(creds)
            for attempt in range(3):
                try:
                    self._spreadsheet = client.open_by_key(self.spreadsheet_id)
                    break
                except gspread.exceptions.APIError as e:
                    if attempt == 2:
                        raise e
                    time.sleep(1)

    def _get_cached_records(self, worksheet_name: str, ttl: Optional[int] = None) -> list[dict]:
        """Отримання записів із гарантованим підключенням та кшуванням"""
        now = datetime.datetime.now()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        
        # 1. Перевірка та повернення даних із кєшу
        if hasattr(self, "_cache") and worksheet_name in self._cache:
            cache_entry = self._cache[worksheet_name]
            if (now - cache_entry["time"]).total_seconds() < effective_ttl:
                return cache_entry["data"]

        try:
            # 2. Гарантоване підключення до Google Sheets API
            self._connect()
            if not self._spreadsheet:
                return []

            ws = self._spreadsheet.worksheet(worksheet_name)

            # 3. Безпечне зчитування всіх рядків
            values = ws.get_all_values()
            if not values or len(values) < 2:
                return []

            headers = [str(h).strip() for h in values[0]]
            records = []

            for row in values[1:]:
                if not any(str(cell).strip() for cell in row):
                    continue

                record = {}
                for idx, header in enumerate(headers):
                    if header:
                        record[header] = str(row[idx]).strip() if idx < len(row) else ""
                records.append(record)

            # 4. Оновлення локального кєшу
            if not hasattr(self, "_cache"):
                self._cache = {}
            self._cache[worksheet_name] = {"time": now, "data": records}

            return records
        except Exception as e:
            print(f"Помилка зчитування листа '{worksheet_name}': {e}")
            return []

            # Используем get_all_values() вместо get_all_records() для обхода дубликатов заголовков
            values = ws.get_all_values()
            if not values or len(values) < 2:
                return []

            headers = [str(h).strip() for h in values[0]]
            records = []

            for row in values[1:]:
                # Пропускаем полностью пустые строки
                if not any(str(cell).strip() for cell in row):
                    continue

                record = {}
                for idx, header in enumerate(headers):
                    # Добавляем значение только если заголовок не пустой
                    if header:
                        record[header] = str(row[idx]).strip() if idx < len(row) else ""
                records.append(record)

            # Обновляем кэш
            if not hasattr(self, "_cache"):
                self._cache = {}
            self._cache[worksheet_name] = {"time": now, "data": records}

            return records
        except Exception as e:
            print(f"Помилка зчитування листа '{worksheet_name}': {e}")
            return []

    def invalidate_cache(self, sheet_name: str = None):
        """Очищення кешу після виконання записів"""
        if sheet_name:
            self._cache.pop(sheet_name, None)
        else:
            self._cache.clear()

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[UserModel]:
        """Шукає користувача в кеші 'Користувачі' з захистом від форматування Google Sheets"""
        records = self._get_cached_records("Користувачі", ttl=2)
        target_id_str = str(telegram_id).strip()

        for row in records:
            # Гнучкий пошук колонки Telegram ID (незалежно від пробілів та регістру)
            raw_tg_id = ""
            for key, val in row.items():
                if str(key).strip().lower() in ["telegram id", "telegram_id", "tg_id", "telegramid"]:
                    # Очищаємо від float-формату (наприклад 413475037.0) та пробілів
                    raw_tg_id = str(val).strip().split('.')[0]
                    break

            if raw_tg_id == target_id_str:
                role = str(row.get("Роль") or row.get("Role") or "").strip()
                status = str(row.get("Статус") or row.get("Status") or "").strip()

                return UserModel(
                    user_id=str(row.get("User ID") or row.get("user_id") or ""),
                    telegram_id=int(telegram_id),
                    role=role,
                    representative_id=row.get("Representative ID") or None,
                    athlete_id=row.get("Athlete ID") or None,
                    trainer_id=row.get("Trainer ID") or None,
                    status=status
                )
        return None

    def get_athlete_by_id(self, athlete_id: str) -> Optional[AthleteModel]:
        """Підтягує профіль спортсмена з кешу 'Спортсмени'"""
        records = self._get_cached_records("Спортсмени")
        for row in records:
            if str(row.get("Athlete ID")) == str(athlete_id):
                return AthleteModel(**row)
        return None

    def update_attendance(self, attendance_id: str, date: str, athlete_id: str, group_id: str, trainer_id: str, status: str, comment: str = ""):
        """Додає або оновлює запис відвідуваності та скидає кеш"""
        self._connect()
        worksheet = self._spreadsheet.worksheet("Відвідування")
        records = self._get_cached_records("Відвідування")
        
        row_index = None
        for idx, row in enumerate(records, start=2):
            if str(row.get("Athlete ID")) == str(athlete_id) and str(row.get("Дата")) == str(date):
                row_index = idx
                break
                
        if row_index:
            worksheet.update_cell(row_index, 6, status)
        else:
            worksheet.append_row([attendance_id, date, athlete_id, group_id, trainer_id, status, comment])
            
        self.invalidate_cache("Відвідування")
        return True

    def update_evaluation(self, evaluation_id: str, date: str, athlete_id: str, group_id: str, trainer_id: str, behavior: int, diligence: int, technique: int, total_score: str, comment: str = ""):
        """Додає або оновлює запис оцінювання та скидає кеш"""
        self._connect()
        worksheet = self._spreadsheet.worksheet("Оцінювання")
        records = self._get_cached_records("Оцінювання")
        
        row_index = None
        for idx, row in enumerate(records, start=2):
            if str(row.get("Athlete ID")) == str(athlete_id) and str(row.get("Дата")) == str(date):
                row_index = idx
                break
                
        row_data = [evaluation_id, date, athlete_id, group_id, trainer_id, behavior, diligence, technique, total_score, comment]

        if row_index:
            try:
                worksheet.update(f"A{row_index}:J{row_index}", [row_data])
            except TypeError:
                worksheet.update(values=[row_data], range_name=f"A{row_index}:J{row_index}", value_input_option='USER_ENTERED')
            
        self.invalidate_cache("Оцінювання")
        return True

    def get_payments_by_athlete(self, athlete_id: str):
        """Повертає історію оплат з кешу 'Оплати'"""
        try:
            records = self._get_cached_records("Оплати")
            return [row for row in records if str(row.get("Athlete ID")) == str(athlete_id)]
        except Exception:
            return []

    def upsert_payment(
        self,
        payment_id: str,
        athlete_id: str,
        representative_id: str,
        group_id: str,
        period: str,
        amount: str,
        payment_date: str,
        status: str,
        comment: str = ""
    ):
        """Додавання або оновлення оплати в Google Таблиці з універсальним виявленням gspread"""
        try:
            ws = None
            
            # 1. Перевірка наявних методів класу
            if hasattr(self, "get_worksheet") and callable(getattr(self, "get_worksheet")):
                ws = self.get_worksheet("Оплати")
            elif hasattr(self, "_get_worksheet") and callable(getattr(self, "_get_worksheet")):
                ws = self._get_worksheet("Оплати")
            
            # 2. Динамічний пошук об'єкта зі збереженим підключенням до Таблиці
            if not ws:
                for attr_name, attr_val in self.__dict__.items():
                    if attr_val is not None and hasattr(attr_val, "worksheet") and callable(getattr(attr_val, "worksheet")):
                        try:
                            ws = attr_val.worksheet("Оплати")
                            break
                        except Exception:
                            continue

            # 3. Якщо підключення не знайдено через звичайні атрибути — виводимо список доступних полів для діагностики
            if not ws:
                available_attrs = list(self.__dict__.keys())
                raise AttributeError(f"Не вдалося знайти підключення до Google Таблиці. Наявні атрибути у SheetsRepository: {available_attrs}")

            records = ws.get_all_records()
            row_idx = None
            
            for idx, r in enumerate(records, start=2):
                if str(r.get("Payment ID", "")).strip() == str(payment_id).strip():
                    row_idx = idx
                    break

            new_row = [
                payment_id,
                athlete_id,
                representative_id,
                group_id,
                period,
                str(amount),
                payment_date,
                status,
                comment
            ]

            if row_idx:
                ws.update(f"A{row_idx}:I{row_idx}", [new_row])
            else:
                ws.append_row(new_row)

            # Інвалідація локального кєшу
            if hasattr(self, "_cache") and isinstance(self._cache, dict):
                self._cache.pop("Оплати", None)

            return True
        except Exception as e:
            print(f"Помилка запису в лист 'Оплати': {e}")
            raise e

    def get_tasks_for_athlete(self, athlete_id: str):
        """Збирає завдання з кешу 'Опис завдання' та 'Досягнення'"""
        try:
            task_templates = self._get_cached_records("Опис завдання")
            achievements = self._get_cached_records("Досягнення")
            
            target_ath_norm = normalize_id(athlete_id)
            athlete_ach = {}
            for row in achievements:
                if normalize_id(row.get("Athlete ID")) == target_ath_norm:
                    p_id_norm = normalize_id(row.get("Progress ID"))
                    athlete_ach[p_id_norm] = row
            
            result = []
            for t in task_templates:
                p_id_raw = str(t.get("Progress ID")).strip()
                p_id_norm = normalize_id(p_id_raw)
                ach = athlete_ach.get(p_id_norm, {})
                
                result.append({
                    "Achievement ID": ach.get("Achievement ID", ""),
                    "Athlete ID": athlete_id,
                    "Progress ID": p_id_raw,
                    "Дата виконання": ach.get("Дата виконання", ""),
                    "Значення виконання": ach.get("Значення виконання", "0"),
                    "STATUS VIKONAN": str(ach.get("STATUS VIKONAN") or "Нове").strip(),
                    "LIFE": str(t.get("LIFE") or "Активне").strip(),
                    "NAME ZAVDAN": t.get("NAME ZAVDAN"),
                    "OPUS ZAVDAN": t.get("OPUS ZAVDAN"),
                    "ZVIT VIK": t.get("ZVIT VIK") or t.get("OPUS ZAVDAN") or "",
                    "Показник": t.get("Показник"),
                    "Одиниця виміру": t.get("Одиниця виміру"),
                    "STIKER ID": t.get("STIKER ID")
                })
            return result
        except Exception as e:
            print(f"Помилка збору завдань: {e}")
            return []

    def upsert_achievement(self, achievement_id: str, athlete_id: str, progress_id: str, date: str, current_value: str, status: str):
        """Оновлює досягнення та скидає кеш"""
        self._connect()
        worksheet = self._spreadsheet.worksheet("Досягнення")
        records = self._get_cached_records("Досягнення")
        
        row_index = None
        target_ath_norm = normalize_id(athlete_id)
        target_prog_norm = normalize_id(progress_id)

        for idx, row in enumerate(records, start=2):
            if normalize_id(row.get("Athlete ID")) == target_ath_norm and normalize_id(row.get("Progress ID")) == target_prog_norm:
                row_index = idx
                break
                
        existing_id = ""
        if row_index and row_index - 2 < len(records):
            existing_id = records[row_index - 2].get("Achievement ID")
            
        final_ach_id = achievement_id or existing_id or str(uuid.uuid4())[:8]
        row_data = [final_ach_id, athlete_id, date, progress_id, "", current_value, "", "", status, ""]

        if row_index:
            try:
                worksheet.update(f"A{row_index}:J{row_index}", [row_data])
            except TypeError:
                worksheet.update(values=[row_data], range_name=f"A{row_index}:J{row_index}")
        else:
            worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            
        self.invalidate_cache("Досягнення")
        return True

    def get_group_name_by_id(self, group_id: str) -> str:
        """Повертає назву групи з кешу 'Групи'"""
        if not group_id:
            return "Основна"
        try:
            records = self._get_cached_records("Групи")
            for row in records:
                if str(row.get("Group ID")).strip() == str(group_id).strip():
                    return str(row.get("Назва групи") or row.get("Назва") or group_id)
        except Exception as e:
            print(f"Помилка отримання групи: {e}")
        return str(group_id)

    def get_trainer_name_by_id(self, trainer_id: str) -> str:
        """Повертає ПІБ тренера з кешу 'Тренери'"""
        if not trainer_id:
            return "Не призначено"
        try:
            records = self._get_cached_records("Тренери")
            for row in records:
                if str(row.get("Trainer ID")).strip() == str(trainer_id).strip():
                    return str(row.get("ПІБ") or row.get("ПІБ тренера") or trainer_id)
        except Exception as e:
            print(f"Помилка отримання тренера: {e}")
        return str(trainer_id)

    def get_competitions(self):
        """Отримує всі записи з кешу 'Змагання'"""
        try:
            return self._get_cached_records("Змагання")
        except Exception as e:
            print(f"Помилка завантаження змагань: {e}")
            return []

    def get_schedule_for_athlete_group(self, group_id: str):
        """Збирає розклад із кешованих даних"""
        try:
            sched_records = self._get_cached_records("Розклад")
            groups_records = self._get_cached_records("Групи")
            schools_records = self._get_cached_records("Школи")

            groups_dict = {str(g.get("Group ID")).strip(): g for g in groups_records}
            schools_dict = {str(s.get("School ID")).strip(): s for s in schools_records}

            result = []
            for s in sched_records:
                s_group_id = str(s.get("Group ID")).strip()
                s_school_id = str(s.get("School ID")).strip()

                if group_id and s_group_id != str(group_id).strip():
                    continue

                grp_info = groups_dict.get(s_group_id, {})
                target_school_id = s_school_id or str(grp_info.get("School ID", "")).strip()
                school_info = schools_dict.get(target_school_id, {})

                result.append({
                    "day": s.get("День"),
                    "start_time": s.get("Початок"),
                    "end_time": s.get("Кінець"),
                    "title": s.get("Назва групи") or grp_info.get("Назва групи", "Тренування"),
                    "group_name": grp_info.get("Назва групи") or grp_info.get("Опис", ""),
                    "hall_name": school_info.get("Назва залу") or school_info.get("Назва") or school_info.get("Назва школи", "Зал №1"),
                    "hall_address": school_info.get("Адреса") or school_info.get("Адреса школи") or ""
                })
            return result
        except Exception as e:
            print(f"Помилка завантаження розкладу: {e}")
            return []

    def get_athlete_sticker_count(self, athlete_id: str) -> str:
        """Повертає значення 'KIL STIKER' з кешу 'Спортсмени'"""
        if not athlete_id:
            return "0"
        try:
            records = self._get_cached_records("Спортсмени")
            target_ath_norm = normalize_id(athlete_id)
            for row in records:
                if normalize_id(row.get("Athlete ID")) == target_ath_norm:
                    val = row.get("KIL STIKER") or row.get("KIL_STIKER")
                    if val is not None and str(val).strip() != "":
                        return str(val).strip()
        except Exception as e:
            print(f"Помилка отримання KIL STIKER: {e}")
        return "0"

    def get_athlete_results_data(self, athlete_id: str):
        """Отримує результати з кешованих даних"""
        try:
            ath_records = self._get_cached_records("Спортсмени")
            res_records = self._get_cached_records("Результати")
            comp_records = self._get_cached_records("Змагання")

            target_ath_norm = normalize_id(athlete_id)
            ath_data = next((row for row in ath_records if normalize_id(row.get("Athlete ID")) == target_ath_norm), {})

            stats = {
                "gold": str(ath_data.get("1M") or "0"),
                "silver": str(ath_data.get("2M") or "0"),
                "bronze": str(ath_data.get("3M") or "0"),
                "medals": str(ath_data.get("MEDAL") or "0"),
                "cups": str(ath_data.get("KUBOK") or "0"),
                "seminars": str(ath_data.get("ATESTAC") or "0"),
                "belt_color": str(ath_data.get("KOLIR POYAS") or "Пояс не вказано"),
                "poyas": str(ath_data.get("POYAS") or ""),
                "kms_ms": str(ath_data.get("KMS MS") or "")
            }

            comp_map = {normalize_id(c.get("Competition ID")): c for c in comp_records}
            results_list = []
            for r in res_records:
                if normalize_id(r.get("Athlete ID")) == target_ath_norm:
                    c_id_norm = normalize_id(r.get("Competition ID"))
                    comp_info = comp_map.get(c_id_norm, {})
                    results_list.append({
                        "result_id": r.get("Result ID"),
                        "competition_id": r.get("Competition ID"),
                        "comp_name": comp_info.get("Назва") or "Змагання",
                        "comp_date": comp_info.get("Дата") or "",
                        "discipline": r.get("Дисципліна") or "",
                        "place": str(r.get("Місце") or "").strip(),
                        "cup": str(r.get("Кубок") or "").strip()
                    })

            return {"stats": stats, "history": results_list}
        except Exception as e:
            print(f"Помилка завантаження результатів: {e}")
            return {"stats": {}, "history": []}

    def get_evaluations_data(self, athlete_id: str):
        """Збирає оцінки спортсмена з кешу 'Оцінювання'"""
        try:
            records = self._get_cached_records("Оцінювання")
            target_ath_norm = normalize_id(athlete_id)
            athlete_evals = [r for r in records if normalize_id(r.get("Athlete ID")) == target_ath_norm]

            def parse_num(val):
                try:
                    return float(str(val).replace(',', '.').strip())
                except (ValueError, TypeError):
                    return 0.0

            months_uk = {1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень", 6: "Червень", 7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень"}
            daily_list = []
            monthly_groups = {}
            current_month_evals = []
            now_m, now_y = 9, 2026

            for r in athlete_evals:
                date_str = str(r.get("Дата") or "").strip()
                b = parse_num(r.get("Поведінка"))
                d = parse_num(r.get("Старанність"))
                t = parse_num(r.get("Техніка"))
                avg = parse_num(r.get("Загальна оцінка"))
                
                if avg == 0 and (b or d or t):
                    avg = round((b + d + t) / 3, 2)

                parts = date_str.split('.')
                month_num, year_num = now_m, now_y
                if len(parts) == 3:
                    month_num = int(parts[1])
                    year_num = int(parts[2])

                m_title = f"{months_uk.get(month_num, 'Місяць')} {year_num}"
                if month_num == now_m and year_num == now_y:
                    current_month_evals.append({"b": b, "d": d, "t": t, "avg": avg})

                daily_list.append({"date": date_str, "behavior": b, "diligence": d, "technique": t, "total_score": round(avg, 2), "comment": r.get("Коментар") or ""})
                if m_title not in monthly_groups:
                    monthly_groups[m_title] = []
                monthly_groups[m_title].append({"b": b, "d": d, "t": t, "avg": avg})

            target_set = current_month_evals if current_month_evals else [{"b": parse_num(r.get("Поведінка")), "d": parse_num(r.get("Старанність")), "t": parse_num(r.get("Техніка")), "avg": parse_num(r.get("Загальна оцінка"))} for r in athlete_evals]
            if target_set:
                top_b = round(sum(x["b"] for x in target_set) / len(target_set), 1)
                top_d = round(sum(x["d"] for x in target_set) / len(target_set), 1)
                top_t = round(sum(x["t"] for x in target_set) / len(target_set), 1)
                top_avg = round(sum(x["avg"] for x in target_set) / len(target_set), 1)
            else:
                top_b = top_d = top_t = top_avg = 0.0

            monthly_list = []
            for m_name, items in monthly_groups.items():
                mb = round(sum(x["b"] for x in items) / len(items), 1)
                md = round(sum(x["d"] for x in items) / len(items), 1)
                mt = round(sum(x["t"] for x in items) / len(items), 1)
                mavg = round(sum(x["avg"] for x in items) / len(items), 1)
                monthly_list.append({"month_name": m_name, "count": len(items), "behavior": mb, "diligence": md, "technique": mt, "total_score": mavg})

            return {"summary": {"avg_total": top_avg, "avg_behavior": top_b, "avg_diligence": top_d, "avg_technique": top_t}, "daily": daily_list, "monthly": monthly_list}
        except Exception as e:
            print(f"Помилка завантаження оцінок: {e}")
            return {"summary": {}, "daily": [], "monthly": []}

    def get_attendance_data(self, athlete_id: str):
        """Збирає відвідуваність з кешу 'Відвідування'"""
        try:
            records = self._get_cached_records("Відвідування")
            target_ath_norm = normalize_id(athlete_id)
            days_uk = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
            history = []
            total = attended = absent = 0

            for r in records:
                if normalize_id(r.get("Athlete ID")) == target_ath_norm:
                    date_str = str(r.get("Дата") or "").strip()
                    status = str(r.get("Статус") or "").strip()
                    total += 1
                    is_ok = status.lower() in ["присутній", "був", "є"]
                    if is_ok:
                        attended += 1
                    else:
                        absent += 1

                    day_prefix = ""
                    try:
                        parts = date_str.split('.')
                        if len(parts) == 3:
                            d_obj = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                            day_prefix = days_uk[d_obj.weekday()]
                    except Exception:
                        day_prefix = ""

                    history.append({
                        "attendance_id": r.get("Attendance ID"),
                        "raw_date": date_str,
                        "display_date": f"{day_prefix} {date_str}".strip(),
                        "status": "Присутній" if is_ok else "Відсутній",
                        "comment": r.get("Коментар") or ""
                    })

            percent = round((attended / total) * 100) if total > 0 else 0
            return {"stats": {"total": total, "attended": attended, "absent": absent, "percent": percent}, "history": history}
        except Exception as e:
            print(f"Помилка завантаження відвідуваності: {e}")
            return {"stats": {"total": 0, "attended": 0, "absent": 0, "percent": 0}, "history": []}

    def get_groups_for_user(self, user_role: str, trainer_id: str = None) -> list:
        """Повертає групи з кешу 'Групи'"""
        try:
            records = self._get_cached_records("Групи")
            groups = []
            for row in records:
                if str(row.get("Статус") or "").strip().lower() == "неактивна":
                    continue
                g_id = str(row.get("Group ID") or "").strip()
                g_name = str(row.get("Назва групи") or "").strip()
                row_trainer = str(row.get("Trainer ID") or "").strip()

                if user_role == "admin":
                    groups.append({"group_id": g_id, "group_name": g_name})
                elif user_role == "trainer":
                    if trainer_id and normalize_id(row_trainer) == normalize_id(trainer_id):
                        groups.append({"group_id": g_id, "group_name": g_name})
            return groups
        except Exception as e:
            print(f"Помилка отримання груп: {e}")
            return []

    def get_athletes_by_group(self, group_id: str) -> list:
        """Повертає спортсменів групи з кешу 'Спортсмени'"""
        try:
            records = self._get_cached_records("Спортсмени")
            athletes = []
            target_group_norm = normalize_id(group_id)

            for row in records:
                if normalize_id(row.get("Group ID")) == target_group_norm:
                    athletes.append({
                        "athlete_id": str(row.get("Athlete ID") or "").strip(),
                        "full_name": str(row.get("ПІБ") or "").strip(),
                        "trainer_id": str(row.get("Trainer ID") or "").strip(),
                        "group_id": str(row.get("Group ID") or "").strip()
                    })
            return athletes
        except Exception as e:
            print(f"Помилка отримання спортсменів: {e}")
            return []

    def bulk_save_group_data(self, group_id: str, items: list) -> bool:
        """Пакетний запис у 'Відвідування' та 'Оцінювання' із збереженням типів (USER_ENTERED)"""
        self._connect()
        try:
            att_ws = self._spreadsheet.worksheet("Відвідування")
            eval_ws = self._spreadsheet.worksheet("Оцінювання")

            today_str = datetime.date.today().strftime("%d.%m.%Y")

            att_rows_to_append = []
            eval_rows_to_append = []

            for item in items:
                athlete_id = str(item.get("athlete_id") or "").strip()
                trainer_id = str(item.get("trainer_id") or "").strip()
                att_status = str(item.get("attendance") or "").strip()
                
                beh_raw = str(item.get("behavior") or "").strip()
                dil_raw = str(item.get("diligence") or "").strip()
                tec_raw = str(item.get("technique") or "").strip()

                # 1. Формування запису у "Відвідування"
                if att_status in ["Присутній", "Відсутній"]:
                    att_rows_to_append.append([
                        str(uuid.uuid4())[:8],
                        today_str,
                        athlete_id,
                        group_id,
                        trainer_id,
                        att_status,
                        "Пакетна відмітка"
                    ])

                # 2. Перетворення оцінок у числовий тип int (або порожній рядок, якщо не вибрано)
                beh_num = int(beh_raw) if beh_raw.isdigit() and 1 <= int(beh_raw) <= 5 else ""
                dil_num = int(dil_raw) if dil_raw.isdigit() and 1 <= int(dil_raw) <= 5 else ""
                tec_num = int(tec_raw) if tec_raw.isdigit() and 1 <= int(tec_raw) <= 5 else ""

                scores = [v for v in [beh_num, dil_num, tec_num] if isinstance(v, int)]

                if scores:
                    avg_score = round(sum(scores) / len(scores), 2)  # Передаємо як float

                    eval_rows_to_append.append([
                        str(uuid.uuid4())[:8],
                        today_str,
                        athlete_id,
                        group_id,
                        trainer_id,
                        beh_num,
                        dil_num,
                        tec_num,
                        avg_score,  # Числовий формат для підрахунків у таблиці
                        "Пакетна оцінка"
                    ])

            # Використовуємо value_input_option='USER_ENTERED' для розпізнавання типів у Google Sheets
            if att_rows_to_append:
                att_ws.append_rows(att_rows_to_append, value_input_option='USER_ENTERED')
                self.invalidate_cache("Відвідування")

            if eval_rows_to_append:
                eval_ws.append_rows(eval_rows_to_append, value_input_option='USER_ENTERED')
                self.invalidate_cache("Оцінювання")

            return True
        except Exception as e:
            print(f"Помилка пакетного збереження даних групи: {e}")
            raise e

    def get_athlete_profile_details(self, athlete_id: str) -> dict:
        """Отримання розширеного профілю спортсмена зі зв'язаними даними про групу та тренера"""
        try:
            records = self._get_cached_records("Спортсмени")
            target_athlete = None
            for r in records:
                if str(r.get("Athlete ID") or "").strip() == str(athlete_id).strip():
                    target_athlete = r
                    break

            if not target_athlete:
                return {}

            # Отримуємо назву групи та ПІБ тренера
            group_id = str(target_athlete.get("Group ID") or "").strip()
            trainer_id = str(target_athlete.get("Trainer ID") or "").strip()

            group_name = self.get_group_name_by_id(group_id) or "Не вказано"
            trainer_name = self.get_trainer_name_by_id(trainer_id) or "Не вказано"

            return {
                "athlete_id": str(target_athlete.get("Athlete ID") or "").strip(),
                "full_name": str(target_athlete.get("ПІБ") or "Не вказано").strip(),
                "dob": str(target_athlete.get("Дата народження") or "").strip(),
                "group_id": group_id,
                "group_name": group_name,
                "trainer_id": trainer_id,
                "trainer_name": trainer_name,
                "phone_athlete": str(target_athlete.get("Телефон Athlete") or "-").strip(),
                "phone_rep": str(target_athlete.get("Телефон Representative") or "-").strip(),
                "vaga": str(target_athlete.get("VAGA") or "-").strip(),
                "kolir_poyas": str(target_athlete.get("KOLIR POYAS") or "").strip(),
                "poyas": str(target_athlete.get("POYAS") or "").strip(),
                "kms_ms": str(target_athlete.get("KMS MS") or "-").strip()
            }
        except Exception as e:
            print(f"Помилка отримання профілю {athlete_id}: {e}")
            return {}

    def update_athlete_profile_data(self, athlete_id: str, vaga: str = None, group_id: str = None) -> bool:
        """Оновлення ваги та групи спортсмена в Google Таблиці"""
        try:
            ws = None
            if hasattr(self, "get_worksheet") and callable(getattr(self, "get_worksheet")):
                ws = self.get_worksheet("Спортсмени")
            else:
                for attr_val in self.__dict__.values():
                    if attr_val is not None and hasattr(attr_val, "worksheet"):
                        try:
                            ws = attr_val.worksheet("Спортсмени")
                            break
                        except Exception:
                            continue

            if not ws:
                raise AttributeError("Не знайдено підключення до листа 'Спортсмени'")

            headers = ws.row_values(1)
            records = ws.get_all_records()

            row_idx = None
            for idx, r in enumerate(records, start=2):
                if str(r.get("Athlete ID", "")).strip() == str(athlete_id).strip():
                    row_idx = idx
                    break

            if not row_idx:
                return False

            # Оновлюємо VAGA
            if vaga is not None and "VAGA" in headers:
                col_idx = headers.index("VAGA") + 1
                ws.update_cell(row_idx, col_idx, str(vaga))

            # Оновлюємо Group ID
            if group_id is not None and "Group ID" in headers:
                col_idx = headers.index("Group ID") + 1
                ws.update_cell(row_idx, col_idx, str(group_id))

            # Очищуємо кєш
            if hasattr(self, "_cache") and isinstance(self._cache, dict):
                self._cache.pop("Спортсмени", None)

            return True
        except Exception as e:
            print(f"Помилка оновлення профілю в БД: {e}")
            raise e

# ... твои существующие методы (_connect, _get_cached_records и т.д.) ...

    def find_athlete_by_pib_and_dob(self, pib: str, dob: str) -> Optional[dict]:
        """Пошук спортсмена в БД за точною відповідністю ПІБ та дати народження"""
        records = self._get_cached_records("Спортсмени")
        clean_pib = str(pib).strip().lower()
        clean_dob = str(dob).strip().lower()

        for r in records:
            r_pib = str(r.get("ПІБ") or "").strip().lower()
            r_dob = str(r.get("Дата народження") or "").strip().lower()
            if r_pib == clean_pib and r_dob == clean_dob:
                return r
        return None

    def create_pending_user(self, telegram_id: int, role: str, athlete_id: str, representative_id: str = "") -> bool:
        """Створення нового запису користувача зі статусом 'Очікує'"""
        try:
            self._connect()
            ws = self._spreadsheet.worksheet("Користувачі")
            
            user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
            created_at = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

            new_row = [
                user_id,
                str(telegram_id),
                role,
                representative_id or "",
                athlete_id,
                "",  # Trainer ID
                "Очікує",
                created_at
            ]

            ws.append_row(new_row, value_input_option='USER_ENTERED')
            self.invalidate_cache("Користувачі")
            return True
        except Exception as e:
            print(f"Помилка створення нового користувача: {e}")
            return False


    def get_athletes_by_telegram_id(self, telegram_id: int | str) -> list[dict]:
        """
        Отримує список усіх спортсменів, прив'язаних до Telegram ID,
        підтягуючи їхні справжні ПІБ з аркуша 'Спортсмени'.
        """
        tg_id_str = str(telegram_id).strip()
        user_records = self._get_cached_records("Користувачі")
        athlete_records = self._get_cached_records("Спортсмени")
        
        # Створюємо словник: Athlete ID -> ПІБ з аркуша "Спортсмени"
        athlete_names = {}
        for a in athlete_records:
            ath_id = str(a.get("Athlete ID") or "").strip()
            pib = str(a.get("ПІБ") or "Спортсмен").strip()
            if ath_id:
                athlete_names[normalize_id(ath_id)] = pib

        athletes = []
        seen_ids = set()

        for r in user_records:
            user_tg = str(r.get("Telegram ID") or r.get("telegram_id") or "").strip().split('.')[0]
            status = str(r.get("Статус") or r.get("status") or "").strip().lower()

            if status == "активний" and user_tg == tg_id_str:
                ath_id_raw = str(r.get("Athlete ID") or r.get("athlete_id") or "").strip()
                norm_ath_id = normalize_id(ath_id_raw)

                if ath_id_raw and norm_ath_id not in seen_ids:
                    seen_ids.add(norm_ath_id)
                    full_name = athlete_names.get(norm_ath_id) or "Спортсмен"
                    athletes.append({
                        "athlete_id": ath_id_raw,
                        "full_name": full_name
                    })
        return athletes

sheets_repo = SheetsRepository()
