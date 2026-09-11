from database.sheets_repository import sheets_repo
from models.user import UserModel
from typing import Optional

class AuthService:
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[UserModel]:
        return sheets_repo.get_user_by_telegram_id(telegram_id)

auth_service = AuthService()