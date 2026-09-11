from fastapi import Header, HTTPException
from typing import Optional
from services.auth_service import auth_service
from models.user import UserModel

async def get_current_user(x_telegram_init_data: Optional[str] = Header(None)) -> UserModel:
    """Перевіряє криптографічний підпис Telegram та повертає об'єкт користувача"""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="InitData header missing")
    
    user_data = auth_service.verify_webapp_init_data(x_telegram_init_data)
    if not user_data:
        raise HTTPException(status_code=403, detail="Invalid Telegram signature")
        
    user = auth_service.get_user_by_telegram_id(user_data.get("id"))
    if not user or user.status != "Активний":
        raise HTTPException(status_code=403, detail="User not active or not found")
        
    return user