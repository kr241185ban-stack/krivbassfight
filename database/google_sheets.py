import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Завантажуємо змінні середовища з файлу .env
load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class SheetsRepository:
    def __init__(self):
        self.creds_file = "credentials.json"
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID")
        self._spreadsheet = None

    def connect(self):
        """Встановлює захищене z'єднання з Google Таблицею за її унікальним ID"""
        if not self.spreadsheet_id:
            raise ValueError("❌ Помилка: SPREADSHEET_ID не знайдено у файлі .env!")
            
        try:
            credentials = Credentials.from_service_account_file(
                self.creds_file, scopes=SCOPES
            )
            client = gspread.authorize(credentials)
            # Використовуємо open_by_key замість назви, щоб уникнути помилок пошуку
            self._spreadsheet = client.open_by_key(self.spreadsheet_id)
            print("✅ Успішне підключення до Google Таблиці!")
        except Exception as e:
            print(f"❌ Помилка підключення до Google API: {e}")
            raise e

    def get_user_by_telegram_id(self, telegram_id: int):
        """
        Шукає користувача в аркуші 'Користувачі' за Telegram ID.
        Повертає словник із даними рядка або None, якщо користувача не знайдено.
        """
        if not self._spreadsheet:
            self.connect()
            
        try:
            worksheet = self._spreadsheet.worksheet("Користувачі")
            records = worksheet.get_all_records()
            
            # Проходимо по рядках аркуша та шукаємо збіг Telegram ID
            for row in records:
                db_telegram_id = row.get("Telegram ID")
                if db_telegram_id and str(db_telegram_id) == str(telegram_id):
                    return row
                    
            return None
        except Exception as e:
            print(f"❌ Помилка читання аркуша 'Користувачі': {e}")
            return None

# --- Тестування роботи модуля напряму ---
if __name__ == "__main__":
    db = SheetsRepository()
    db.connect()
    
    # Приклад перевірки (можеш підставити свій тестовий Telegram ID)
    test_tg_id = 413475037 
    user = db.get_user_by_telegram_id(test_tg_id)
    
    if user:
        print(f"🎉 Користувача знайдено: Роль -> {user.get('Роль')}")
    else:
        print("⚠️ Користувача з таким Telegram ID не знайдено в базі.")