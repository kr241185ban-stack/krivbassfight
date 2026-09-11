import gspread
from google.oauth2.service_account import Credentials
from config import config

class GoogleSheetsService:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        # Права доступа для чтения и записи
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        self.credentials = Credentials.from_service_account_file(
            credentials_file, scopes=scopes
        )
        self.client = gspread.authorize(self.credentials)
        self.spreadsheet_id = spreadsheet_id
        
        # Открываем саму таблицу
        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)

    def get_all_trainers(self):
        """Возвращает всех тренеров (тестовый метод)"""
        sheet = self.spreadsheet.worksheet("Тренери")
        return sheet.get_all_records()

    def get_trainer_groups(self, trainer_id: str):
        """
        Получает список групп конкретного тренера.
        Полезно, чтобы Олександр Бобков или В’ячеслав Новицький 
        видели в интерфейсе только своих спортсменов.
        """
        sheet = self.spreadsheet.worksheet("Групи")
        all_groups = sheet.get_all_records()
        # Фильтруем группы по ID тренера
        return [group for group in all_groups if str(group.get("Trainer ID")) == trainer_id]

    def get_athletes_by_group(self, group_id: str):
        """Получает список спортсменов конкретной группы"""
        sheet = self.spreadsheet.worksheet("Спортсмени")
        all_athletes = sheet.get_all_records()
        # Фильтруем только активных бойцов нужной группы
        return [
            athlete for athlete in all_athletes 
            if str(athlete.get("Group ID")) == group_id and athlete.get("Статус") == "Активний"
        ]

    def batch_append_attendance(self, rows_to_add: list[list]):
        """
        Пакетное добавление записей о посещаемости.
        rows_to_add - это список списков (массив строк).
        Записывает 20-30 отметок за 1 вызов к Google API!
        """
        sheet = self.spreadsheet.worksheet("Відвідування")
        # value_input_option='USER_ENTERED' заставляет гугл воспринимать даты как даты
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')

    def batch_append_evaluations(self, rows_to_add: list[list]):
        """
        Пакетне додавання записів про оцінки.
        Записує масив оцінок за одне звернення до Google API.
        """
        sheet = self.spreadsheet.worksheet("Оцінювання")
        sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')

    # ==========================================
    # МОДУЛЬ ГЕЙМІФІКАЦІЇ (СТИКЕРИ ТА ЗАВДАННЯ)
    # ==========================================

    def get_all_tasks(self):
        """Отримує повний каталог завдань/нормативів для гейміфікації"""
        sheet = self.spreadsheet.worksheet("Опис_завдання")
        return sheet.get_all_records()

    def get_athlete_achievements(self, athlete_id: str):
        """Отримує всі досягнення (стикер-бейджі) конкретного спортсмена"""
        sheet = self.spreadsheet.worksheet("Досягнення")
        records = sheet.get_all_records()
        # Повертаємо лише ті записи, які належать цьому спортсмену
        return [r for r in records if str(r.get("Athlete ID")) == athlete_id]

    def append_achievement(self, row_data: list):
        """
        Додає нову заявку на виконання завдання (Спортсмен натиснув 'Виконав').
        Статус за замовчуванням буде 'В очікуванні'.
        """
        sheet = self.spreadsheet.worksheet("Досягнення")
        sheet.append_row(row_data, value_input_option='USER_ENTERED')

    def verify_achievement(self, achievement_id: str, new_status: str):
        """
        Тренер верифікує завдання. 
        Шукаємо рядок за Achievement ID і оновлюємо колонку статусу.
        """
        sheet = self.spreadsheet.worksheet("Досягнення")
        
        # 1. Шукаємо клітинку з потрібним ID у 1-й колонці
        cell = sheet.find(achievement_id, in_column=1)
        
        if cell:
            row_index = cell.row
            
            # 2. Колонка "STATUS VIKONAN" знаходиться під номером 9.
            # (Achievement ID, Athlete ID, Дата, Progress ID, NAME ZAVDAN, Значення, Показник, Одиниця, STATUS VIKONAN, STIKER ID)
            sheet.update_cell(row_index, 9, new_status)
            return True
            
        return False

# Создаем единственный экземпляр сервиса (паттерн Singleton)
sheets_service = GoogleSheetsService('credentials.json', config.spreadsheet_id)