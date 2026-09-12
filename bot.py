import asyncio
import datetime
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types.web_app_info import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uvicorn

from config import config
from services.auth_service import auth_service
from database.sheets_repository import sheets_repo
from api import app  # Імпорт вашого FastAPI додатка

bot = Bot(token=config.bot_token)
dp = Dispatcher()

# ==========================================
# 1. СТАНИ РЕЄСТРАЦІЇ (FSM)
# ==========================================
class RegistrationStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_pib = State()
    waiting_for_dob = State()


# ==========================================
# 2. АВТОРИЗАЦІЯ ТА ОНБОРДИНГ (/start)
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_tg_id = message.from_user.id
    await state.clear()

    try:
        user = await asyncio.to_thread(auth_service.get_user_by_telegram_id, user_tg_id)

        if user and str(user.status).strip().lower() == "активний":
            
            # 🎯 ПЕРЕВІРКА ДЛЯ ПРЕДСТАВНИКІВ/БАТЬКІВ
            if user.role in ["representative", "parent"]:
                athletes = await asyncio.to_thread(sheets_repo.get_athletes_by_telegram_id, user_tg_id)
                
                if athletes:
                    builder = InlineKeyboardBuilder()
                    
                    for ath in athletes:
                        ath_id = ath.get("athlete_id")
                        ath_name = ath.get("full_name") or "Спортсмен"
                        
                        web_app_url = f"https://krivbassfight.vercel.app/index.html?tg_id={user_tg_id}&athlete_id={ath_id}"
                        builder.button(
                            text=f"👦 {ath_name}",
                            web_app=WebAppInfo(url=web_app_url)
                        )
                    
                    builder.adjust(1)
                    await message.answer(
                        "👨‍👩‍👦 **Вітаємо! Оберіть спортсмена для перегляду кабінету:**",
                        reply_markup=builder.as_markup(),
                        parse_mode="Markdown"
                    )
                    return

            # 🎯 ДЛЯ ОДНОГО СПОРТСМЕНА, ТРЕНЕРА АБО АДМІНА
            web_app_url = f"https://krivbassfight.vercel.app/index.html?tg_id={user_tg_id}"
            if hasattr(user, 'athlete_id') and user.athlete_id:
                web_app_url += f"&athlete_id={user.athlete_id}"

            web_app_button = KeyboardButton(text="Відкрити додаток 🥋", web_app=WebAppInfo(url=web_app_url))
            keyboard = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, is_persistent=True)

            role_messages = {
                "admin": "Ви зайшли як **Адміністратор**.",
                "trainer": "Вітаємо, тренер!",
                "athlete": "Вітаємо тебе! Швиденько заходь у свій кабінет!"
            }
            welcome_text = role_messages.get(user.role, "Вітаємо у Рукопашнику!")
            await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
            return

        if user and str(user.status).strip().lower() in ["очікує", "pending"]:
            await message.answer("⏳ Ваша заявка скоро активується. Очікуйте підтвердження та повідомлення від нас!")
            return

        role_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="👦 Спортсмен")],
                [KeyboardButton(text="👨‍👩‍👦 Представник (Батьки)")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "Вітаємо у системі Школи єдиноборств 'Рукопашник'!\n\nОберіть, хто реєструється:",
            reply_markup=role_keyboard
        )
        await state.set_state(RegistrationStates.waiting_for_role)

    except Exception as e:
        print(f"Помилка при обробці /start: {e}")
        await message.answer("⚠️ Тимчасова помилка зв'язку з базою даних. Натисніть /start ще раз.")


# КРОК 1: Вибір ролі
@dp.message(RegistrationStates.waiting_for_role)
async def process_role_choice(message: Message, state: FSMContext):
    text = message.text.strip()
    if "Спортсмен" in text:
        role = "athlete"
    elif "Представник" in text:
        role = "representative"
    else:
        await message.answer("Будь ласка, оберіть варіант за допомогою кнопок нижче.")
        return

    await state.update_data(chosen_role=role)
    await message.answer(
        "Введіть повне **ПІБ спортсмена** (наприклад: *Бобков Олександр Миколайович*):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(RegistrationStates.waiting_for_pib)


# КРОК 2: Введення ПІБ
@dp.message(RegistrationStates.waiting_for_pib)
async def process_pib_entry(message: Message, state: FSMContext):
    pib = message.text.strip()
    if len(pib) < 5 or " " not in pib:
        await message.answer("⚠️ Будь ласка, введіть коректне ПІБ (прізвище та ім'я).")
        return

    await state.update_data(athlete_pib=pib)
    await message.answer(
        "Введіть **Дату народження спортсмена** у форматі `ДД.ММ.РРРР` (наприклад: `12.03.2015`):",
        parse_mode="Markdown"
    )
    await state.set_state(RegistrationStates.waiting_for_dob)


# КРОК 3: Введення Дати народження та перевірка в БД
@dp.message(RegistrationStates.waiting_for_dob)
async def process_dob_entry(message: Message, state: FSMContext):
    dob = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", dob):
        await message.answer("⚠️ Некоректний формат дати. Введіть дату у форматі `ДД.ММ.РРРР`.", parse_mode="Markdown")
        return

    user_data = await state.get_data()
    role = user_data.get("chosen_role")
    pib = user_data.get("athlete_pib")

    await message.answer("🔍 Перевірка даних у базі клубу...")

    athlete = await asyncio.to_thread(sheets_repo.find_athlete_by_pib_and_dob, pib, dob)

    if not athlete:
        await message.answer(
            "❌ **Спортсмена не знайдено.**\n\n"
            "Перевірте правильність написання ПІБ та дати народження. Дані мають відповідати анкеті.\n"
            "Спробуйте ще раз за допомогою команди /start або зверніться до тренера.",
            parse_mode="Markdown"
        )
        await state.clear()
        return

    athlete_id = str(athlete.get("Athlete ID") or "").strip()
    rep_id = str(athlete.get("Representative ID") or "").strip() if role == "representative" else ""

    success = await asyncio.to_thread(
        sheets_repo.create_pending_user,
        telegram_id=message.from_user.id,
        role=role,
        athlete_id=athlete_id,
        representative_id=rep_id
    )

    await state.clear()

    if success:
        await message.answer(
            "✅ **Анкету успішно знайдено!**\n\n"
            "Заявку на реєстрацію передано нам. Очікуйте підтвердження доступу та повідомлення",
            parse_mode="Markdown"
        )
        if config.trainer_chat_id:
            try:
                msg = (
                    f"🆕 **Нова заявка на реєстрацію!**\n\n"
                    f"👤 **Спортсмен:** {pib}\n"
                    f"🎭 **Роль:** {'Представник' if role == 'representative' else 'Спортсмен'}\n"
                    f"🆔 **Athlete ID:** `{athlete_id}`\n"
                    f"📱 **TG ID:** `{message.from_user.id}`\n\n"
                    f"📌 *Змініть статус користувача на 'Активний' у Google Таблиці.*"
                )
                await bot.send_message(chat_id=int(config.trainer_chat_id), text=msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Помилка сповіщення адміну: {e}")
    else:
        await message.answer("❌ Помилка при збереженні заявки. Спробуйте пізніше.")


# ==========================================
# 3. МАСОВА РОЗСИЛКА (/all)
# ==========================================
@dp.message(Command("all"))
async def cmd_broadcast_all(message: Message):
    if str(message.chat.id) != str(config.trainer_chat_id):
        return

    raw_text = message.caption or message.text or ""
    command_args = raw_text.split(maxsplit=1)
    broadcast_text = command_args[1].strip() if len(command_args) > 1 else ""
    photo_file_id = message.photo[-1].file_id if message.photo else None

    if not broadcast_text and not photo_file_id:
        await message.reply("⚠️ Вкажіть текст розсилки після `/all` або додайте фото з підписом.", parse_mode="Markdown")
        return

    users = await asyncio.to_thread(sheets_repo._get_cached_records, "Користувачі")
    sent_count, fail_count = 0, 0
    status_msg = await message.reply("⏳ Розпочинаю розсилку...")

    for u in users:
        status = str(u.get("Статус") or "").strip().lower()
        tg_id_raw = str(u.get("Telegram ID") or "").strip().split('.')[0]

        if status == "активний" and tg_id_raw.isdigit():
            try:
                caption_text = f"📢 <b>Оголошення від тренерів:</b>\n\n{broadcast_text}" if broadcast_text else "📢 <b>Оголошення від тренерів</b>"
                if photo_file_id:
                    await bot.send_photo(chat_id=int(tg_id_raw), photo=photo_file_id, caption=caption_text, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id=int(tg_id_raw), text=caption_text, parse_mode="HTML")
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception:
                fail_count += 1

    await status_msg.edit_text(
        f"✅ <b>Розсилку завершено!</b>\n\n📨 Доставлено: <b>{sent_count}</b>\n❌ Не доставлено: <b>{fail_count}</b>",
        parse_mode="HTML"
    )


# ==========================================
# 4. ВІДПОВІДЬ ТРЕНЕРА ЧЕРЕЗ REPLY
# ==========================================
@dp.message(F.chat.id == int(config.trainer_chat_id or 0), F.reply_to_message)
async def handle_trainer_reply(message: Message):
    original_text = message.reply_to_message.text or message.reply_to_message.caption or ""

    match = re.search(r"TG ID:\s*(\d+)", original_text)
    if not match:
        return

    target_tg_id = int(match.group(1))
    reply_text = (message.caption or message.text or "").strip()
    photo_file_id = message.photo[-1].file_id if message.photo else None

    if not reply_text and not photo_file_id:
        return

    try:
        caption_text = f"💬 <b>Відповідь від тренера:</b>\n\n{reply_text}" if reply_text else "💬 <b>Відповідь від тренера</b>"

        if photo_file_id:
            await bot.send_photo(chat_id=target_tg_id, photo=photo_file_id, caption=caption_text, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=target_tg_id, text=caption_text, parse_mode="HTML")

        await message.react([{"type": "emoji", "emoji": "👍"}])
    except Exception as e:
        print(f"Помилка відправки відповіді {target_tg_id}: {e}")
        await message.reply("❌ Не вдалося доставити повідомлення спортсмену.")


# ==========================================
# 5. ПРИЙОМ ФОТО ВІД СПОРТСМЕНА В ЧАТІ БОТА
# ==========================================
@dp.message(F.chat.type == "private", F.photo)
async def handle_private_photo_from_athlete(message: Message):
    user_tg_id = message.from_user.id

    user = await asyncio.to_thread(auth_service.get_user_by_telegram_id, user_tg_id)
    if not user or str(user.status).strip().lower() != "активний":
        await message.answer("⚠️ Ваш акаунт не знайдено або він неактивний.")
        return

    sender_name = "Спортсмен"
    group_name = "Основна"
    athlete_id = user.athlete_id or "-"

    if user.athlete_id:
        profile = await asyncio.to_thread(sheets_repo.get_athlete_profile_details, user.athlete_id)
        sender_name = profile.get("full_name", "Спортсмен")
        group_name = profile.get("group_name", "Основна")

    photo_file_id = message.photo[-1].file_id
    user_caption = message.caption or ""

    caption_text = (
        f"📸 <b>Нове фото від спортсмена!</b>\n\n"
        f"👤 <b>Від кого:</b> {sender_name}\n"
        f"♧ <b>Група:</b> {group_name}\n"
        f"🆔 <b>Athlete ID:</b> <code>{athlete_id}</code>\n"
        f"📱 <b>TG ID:</b> <code>{user_tg_id}</code>\n"
    )
    if user_caption:
        caption_text += f"\n💬 <b>Коментар:</b> {user_caption}\n"

    caption_text += "\n<i>💡 Щоб відповісти спортсмену, зробіть Reply (Відповісти) на це повідомлення.</i>"

    try:
        await bot.send_photo(chat_id=int(config.trainer_chat_id), photo=photo_file_id, caption=caption_text, parse_mode="HTML")
        await message.reply("✅ <b>Дякуємо!</b> Твоє фото успішно передано тренерському складу 📸", parse_mode="HTML")
    except Exception as e:
        print(f"Помилка відправки фото тренерам: {e}")
        await message.reply("❌ Не вдалося передати фото тренерам.")


# ==========================================
# ПРИЙОМ ВІДЕО ТА КРУЖЕЧКІВ ВІД СПОРТСМЕНА
# ==========================================
@dp.message(F.chat.type == "private", F.video | F.video_note)
async def handle_private_video_from_athlete(message: Message):
    user_tg_id = message.from_user.id

    user = await asyncio.to_thread(auth_service.get_user_by_telegram_id, user_tg_id)
    if not user or str(user.status).strip().lower() != "активний":
        await message.answer("⚠️ Ваш акаунт не знайдено або він неактивний.")
        return

    sender_name = "Спортсмен"
    group_name = "Основна"
    athlete_id = user.athlete_id or "-"

    if user.athlete_id:
        profile = await asyncio.to_thread(sheets_repo.get_athlete_profile_details, user.athlete_id)
        sender_name = profile.get("full_name", "Спортсмен")
        group_name = profile.get("group_name", "Основна")

    user_caption = message.caption or ""
    caption_text = (
        f"🎥 <b>Нове відео від спортсмена!</b>\n\n"
        f"👤 <b>Від кого:</b> {sender_name}\n"
        f"♧ <b>Група:</b> {group_name}\n"
        f"🆔 <b>Athlete ID:</b> <code>{athlete_id}</code>\n"
        f"📱 <b>TG ID:</b> <code>{user_tg_id}</code>\n"
    )
    if user_caption:
        caption_text += f"\n💬 <b>Коментар:</b> {user_caption}\n"

    caption_text += "\n<i>💡 Щоб відповісти спортсмену, зробіть Reply (Відповісти) на це повідомлення.</i>"

    try:
        if message.video:
            # Звичайне відео з підписом
            await bot.send_video(
                chat_id=int(config.trainer_chat_id),
                video=message.video.file_id,
                caption=caption_text,
                parse_mode="HTML"
            )
        elif message.video_note:
            # Відеоповідомлення (кружечок) — спочатку текстовий підпис, потім кружечок
            await bot.send_message(chat_id=int(config.trainer_chat_id), text=caption_text, parse_mode="HTML")
            await bot.send_video_note(chat_id=int(config.trainer_chat_id), video_note=message.video_note.file_id)

        await message.reply("✅ <b>Дякуємо!</b> Твоє відео успішно передано тренерському складу 🎥", parse_mode="HTML")
    except Exception as e:
        print(f"Помилка відправки відео тренерам: {e}")
        await message.reply("❌ Не вдалося передати відео тренерам.")


# ==========================================
# 6. ОДНОЧАСНИЙ ЗАПУСК БОТА ТА FASTAPI
# ==========================================
async def main():
    config_uvicorn = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config_uvicorn)
    
    print("🚀 Запуск Telegram бота та REST API (FastAPI) на порту 8000...")
    
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот зупинений.")
