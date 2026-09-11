# Файл: api/app.py
from fastapi import Depends
from api.dependencies import get_current_user
from models.user import UserModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # <--- Додано імпорт
from api.routers import trainer
from api.routers import gamification


app = FastAPI(title="Rukopashnik CRM API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trainer.router, prefix="/api/v1/trainer", tags=["Trainer Dashboard"])
app.include_router(gamification.router, prefix="/api/v1/gamification", tags=["Gamification & Badges"])

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "code": 200}

@app.get("/api/v1/me")
async def get_my_profile(user: UserModel = Depends(get_current_user)):
    """Повертає профіль поточного користувача на основі Telegram initData"""
    # Завдяки Depends(get_current_user), сюди дійде тільки авторизований юзер
    return user

# Підключаємо папку з фронтендом (Mini App)
# Тепер файли будуть доступні за адресою /webapp/index.html
app.mount("/webapp", StaticFiles(directory="webapp"), name="webapp")