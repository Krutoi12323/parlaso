import asyncio
import logging
import os
import sys
import math
import time
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BufferedInputFile,
    BotCommandScopeDefault, BotCommandScopeChat
)
from aiogram.types import CallbackQuery, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiocryptopay import AioCryptoPay, Networks

API_TOKEN = os.environ["API_TOKEN"]
CRYPTO_BOT_TOKEN = os.environ["CRYPTO_BOT_TOKEN"]

# Ваш числовой Telegram ID (только у него есть доступ к /admin)
ADMIN_ID = 8400589097 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

POOL_FILE = "global_pool.txt"
PROMO_FILE = "Promo.txt"
USERS_FILE = "users_stats.txt"
ALL_USERS_FILE = "all_users.txt"
NOTIFY_FILE = "no_notifications.txt" 
PRICES_FILE = "prices.json"

# ================= СИСТЕМА ЦЕНООБРАЗОВАНИЯ =================
def load_prices() -> dict:
    default_prices = {
        "star_rub": 1.52,
        "star_usdt": 0.015,
        "prem_3_rub": 1250,
        "prem_3_usdt": 13.00,
        "prem_6_rub": 1700,
        "prem_6_usdt": 17.50,
        "prem_12_rub": 2999,
        "prem_12_usdt": 31.00,
        "star_presets": [50, 100, 250, 400, 500, 1000]
    }
    if not os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(default_prices, f, ensure_ascii=False, indent=4)
        return default_prices
    
    try:
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in default_prices.items():
            if k not in data:
                data[k] = v
        return data
    except:
        return default_prices

def save_prices(prices_dict):
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(prices_dict, f, ensure_ascii=False, indent=4)

# ================= УПРАВЛЕНИЕ УВЕДОМЛЕНИЯМИ =================
def get_notify_kb(is_enabled: bool):
    if is_enabled:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔕 Отключить уведомления", callback_data="toggle_notify")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Включить уведомления", callback_data="toggle_notify")]
        ])

def toggle_notify_status(user_id: int) -> bool:
    disabled_users = set()
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, "r", encoding="utf-8") as f:
            disabled_users = set(f.read().splitlines())
    
    user_str = str(user_id)
    if user_str in disabled_users:
        disabled_users.remove(user_str)
        new_status = True 
    else:
        disabled_users.add(user_str)
        new_status = False 
        
    with open(NOTIFY_FILE, "w", encoding="utf-8") as f:
        for uid in disabled_users:
            f.write(f"{uid}\n")
            
    return new_status

@dp.callback_query(F.data == "toggle_notify")
async def toggle_notify_handler(c: CallbackQuery):
    new_status = toggle_notify_status(c.from_user.id)
    try:
        await c.message.edit_reply_markup(reply_markup=get_notify_kb(new_status))
    except:
        pass
    if new_status:
        await c.answer("🔔 Уведомления о статусе бота ВКЛЮЧЕНЫ!", show_alert=True)
    else:
        await c.answer("🔕 Уведомления о статусе бота ОТКЛЮЧЕНЫ!", show_alert=True)


# ================= УВЕДОМЛЕНИЯ О СТАТУСЕ БОТА =================
def get_all_user_ids() -> list:
    users = []
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    uid = line.split(":", 1)[0]
                    users.append(uid)
    return users

async def on_startup(bot: Bot):
    if os.path.exists("restart.tmp"):
        try:
            with open("restart.tmp", "r") as f:
                data = f.read().strip().split(":")
                old_time = float(data[0])
                msg_id = int(data[1]) if len(data) > 1 else None
            os.remove("restart.tmp")
            
            restart_duration = round(time.time() - old_time, 2)
            t1 = time.time()
            await bot.get_me()
            ping = int((time.time() - t1) * 1000)

            if ADMIN_ID != 0:
                report_text = (
                    f"🔄 <b>Сигнал получен.</b>\n\n"
                    f"📊 Статус: <b>Готов к работе</b>\n"
                    f"🏓 Пинг API: <b>{ping} мс</b>\n"
                    f"⏱ Время перезапуска: <b>{restart_duration} сек</b>"
                )
                if msg_id:
                    try:
                        await bot.edit_message_text(chat_id=ADMIN_ID, message_id=msg_id, text=report_text)
                    except Exception:
                        await bot.send_message(ADMIN_ID, report_text)
                else:
                    await bot.send_message(ADMIN_ID, report_text)
        except Exception as e:
            logging.error(f"Ошибка при расчете времени перезапуска: {e}")

    users = get_all_user_ids()
    if str(ADMIN_ID) not in users:
        users.append(str(ADMIN_ID))

    disabled_users = set()
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, "r", encoding="utf-8") as f:
            disabled_users = set(f.read().splitlines())

    for uid in users:
        if (uid in disabled_users) or (int(uid) == ADMIN_ID and os.path.exists("restart.tmp") == False):
            if int(uid) != ADMIN_ID:
                continue 
        
        try:
            if int(uid) != ADMIN_ID or not 'restart_duration' in locals():
                await bot.send_message(
                    int(uid), 
                    "🟢 <b>Бот успешно запущен и готов к работе!</b>",
                    reply_markup=get_notify_kb(True)
                )
            await asyncio.sleep(0.05) 
        except Exception:
            pass

async def on_shutdown(bot: Bot):
    users = get_all_user_ids()
    if str(ADMIN_ID) not in users:
        users.append(str(ADMIN_ID))

    disabled_users = set()
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, "r", encoding="utf-8") as f:
            disabled_users = set(f.read().splitlines())

    for uid in users:
        if uid in disabled_users and int(uid) != ADMIN_ID:
            continue
        try:
            await bot.send_message(
                int(uid), 
                "🔴 <b>Бот остановлен! Временно не принимает заказы.</b>",
                reply_markup=get_notify_kb(True)
            )
            await asyncio.sleep(0.05)
        except Exception:
            pass

dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

# ================= БАЗА ПОЛЬЗОВАТЕЛЕЙ =================
def save_user_to_db(user: types.User):
    users = {}
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split(":", 1)
                if len(parts) == 2:
                    users[parts[0]] = parts[1]
                else:
                    users[parts[0]] = "" 
    
    uid_str = str(user.id)
    uname = user.username if user.username else ""
    
    if uid_str not in users or users[uid_str] != uname:
        users[uid_str] = uname
        with open(ALL_USERS_FILE, "w", encoding="utf-8") as f:
            for k, v in users.items():
                f.write(f"{k}:{v}\n")

def get_user_id_by_username(username: str):
    target = username.lower().replace("@", "").replace("t.me/", "").replace("https://", "")
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[1].lower() == target:
                    return int(parts[0])
    return None

# Функция чтения промокодов
def load_promos() -> dict:
    promos = {}
    if not os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "w", encoding="utf-8") as f:
            f.write("# Формат: ПРОМОКОД:тип:значение:лимит_активаций\n")
    
    with open(PROMO_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) == 4:
                code, p_type, val_str, limit_str = parts[0].strip().upper(), parts[1].strip().lower(), parts[2].strip(), parts[3].strip()
                if val_str.isdigit():
                    promos[code] = {
                        "type": p_type,
                        "value": int(val_str),
                        "limit": limit_str if limit_str == "inf" else int(limit_str) if limit_str.isdigit() else 1
                    }
    return promos

def add_promo_to_file(code: str, p_type: str, value: int, limit: str):
    if not os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "w", encoding="utf-8") as f:
            f.write("# Формат: ПРОМОКОД:тип:значение:лимит_активаций\n")
            
    with open(PROMO_FILE, "a", encoding="utf-8") as f:
        f.write(f"{code.upper()}:{p_type}:{value}:{limit}\n")

def delete_promo_from_file(target_code: str) -> bool:
    if not os.path.exists(PROMO_FILE):
        return False
    
    with open(PROMO_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    deleted = False
    target = target_code.strip().upper()
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        
        parts = stripped.split(":")
        if len(parts) == 4 and parts[0].strip().upper() == target:
            deleted = True
            continue
        else:
            new_lines.append(line)
            
    if deleted:
        with open(PROMO_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
    return deleted

def update_promo_file_after_use(target_code: str) -> int:
    if not os.path.exists(PROMO_FILE):
        return -1
    
    with open(PROMO_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    remaining_limit = -1
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        
        parts = stripped.split(":")
        if len(parts) == 4 and parts[0].strip().upper() == target_code:
            p_type, val_str, limit_str = parts[1].strip().lower(), parts[2].strip(), parts[3].strip()
            if limit_str != "inf" and limit_str.isdigit():
                left = int(limit_str) - 1
                remaining_limit = left
                if left > 0:
                    new_lines.append(f"{target_code}:{p_type}:{val_str}:{left}\n")
            else:
                remaining_limit = "inf"
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    with open(PROMO_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    return remaining_limit

# Работа со статистикой покупок
def save_user_purchase(user_id: int, p_type: str, amount: int, recipient: str):
    with open(USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}:{p_type}:{amount}:{recipient}\n")

def get_user_stats(user_id: int) -> dict:
    total_stars = 0
    total_prem = 0
    stars_history = []
    prem_history = []
    
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) == 4:
                    uid, p_type, amount, recipient = parts[0], parts[1], parts[2], parts[3]
                    if uid == str(user_id):
                        if p_type == "stars":
                            amt = int(amount)
                            total_stars += amt
                            stars_history.append(f"💎 {amt} ⭐️\n└ Получатель: <b>{recipient}</b>")
                        elif p_type == "premium":
                            mo = int(amount)
                            total_prem += 1
                            prem_history.append(f"⭐ Telegram Premium ({mo} мес.)\n└ Получатель: <b>{recipient}</b>")
                            
    return {
        "stars": total_stars,
        "prem_count": total_prem,
        "stars_history": stars_history,
        "prem_history": prem_history
    }

user_requests_history = {}
user_banned_until = {}

def get_global_pool() -> int:
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            val = f.read().strip()
            if val.isdigit():
                return int(val)
    set_global_pool(10000)
    return 10000

def set_global_pool(amount: int):
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        f.write(str(amount))

class BuySteps(StatesGroup):
    waiting_for_amount = State()
    waiting_for_promo = State()
    waiting_for_recipient_stars = State()
    waiting_for_recipient_prem = State()
    
    admin_promo_code = State()
    admin_promo_type = State()
    admin_promo_value = State()
    admin_promo_limit = State()

class AdminSteps(StatesGroup):
    waiting_for_comment = State()
    waiting_for_broadcast = State()
    waiting_for_pool = State()
    waiting_for_price = State()
    waiting_for_star_presets = State()

# Кнопки главного меню (динамические собираются в функциях)
b1 = InlineKeyboardButton(text="💎 Купить Звезды", callback_data="buy_stars")
b2 = InlineKeyboardButton(text="⭐ Купить Premium", callback_data="buy_premium")
b3 = InlineKeyboardButton(text="👤 Профиль", callback_data="profile")
b4 = InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="use_promo")
b5 = InlineKeyboardButton(text="❓ Помощь", callback_data="help")
b6 = InlineKeyboardButton(text="💼 О боте", callback_data="about")
bc = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
btn_back = InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
btn_back_profile = InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="profile")

main_kb = InlineKeyboardMarkup(inline_keyboard=[[b1], [b2], [b3, b4], [b5, b6]])
cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[bc]])

def get_prem_kb():
    p = load_prices()
    p3 = InlineKeyboardButton(text=f"3 мес — {p['prem_3_rub']} ₽", callback_data="premium_3")
    p6 = InlineKeyboardButton(text=f"6 мес — {p['prem_6_rub']} ₽", callback_data="premium_6")
    p12 = InlineKeyboardButton(text=f"1 год — {p['prem_12_rub']} ₽", callback_data="premium_12")
    return InlineKeyboardMarkup(inline_keyboard=[[p3], [p6], [p12], [btn_back]])

def get_stars_kb():
    p = load_prices()
    r = p["star_rub"]
    presets = p.get("star_presets", [50, 100, 250, 400, 500, 1000])
    
    buttons = []
    row = []
    for amt in presets:
        price = math.ceil(amt * r)
        row.append(InlineKeyboardButton(text=f"{amt} ⭐️  {price} ₽", callback_data=f"preset_{amt}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton(text="Своё количество", callback_data="custom_amount")])
    buttons.append([btn_back])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.update.outer_middleware()
async def ddos_protection_middleware(handler, event, data):
    user = None
    if isinstance(event, types.Message) and event.from_user:
        user = event.from_user
    elif isinstance(event, types.CallbackQuery) and event.from_user:
        user = event.from_user

    if user and user.id != ADMIN_ID:
        now = time.time()
        banned_until = user_banned_until.get(user.id, 0)
        if banned_until:
            if now < banned_until:
                if isinstance(event, types.CallbackQuery):
                    await event.answer("⚠️ Вы заблокированы за флуд!", show_alert=True)
                return
            else:
                user_banned_until.pop(user.id, None)

        history = user_requests_history.setdefault(user.id, [])
        history = [t for t in history if now - t < 1.0]
        history.append(now)
        user_requests_history[user.id] = history

        if len(history) > 5:
            user_banned_until[user.id] = now + 60
            user_requests_history[user.id] = []
            if isinstance(event, types.CallbackQuery):
                await event.answer("⚠️ Слишком много запросов! Бан на 1 минуту.", show_alert=True)
            return

    return await handler(event, data)

@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    save_user_to_db(m.from_user)
    
    text = (
        "👋 <b>Привет!</b>\n\n"
        "Я бот для покупки Telegram Stars и Telegram Premium (Tether/Карта РФ/СБП/Звезды).\n\n"
        "🕒 <b>График работы (выдача/поддержка):</b> с 09:00 до 00:00\n\n"
        "Выберите действие 👇"
    )
    await m.answer(text=text, reply_markup=main_kb)


# ================= СЕКРЕТНАЯ АДМИН ПАНЕЛЬ (/admin) =================

def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Топ покупателей", callback_data="admin_leaderboard"),
         InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast_start"),
         InlineKeyboardButton(text="🎟 Доб. промокод", callback_data="admin_add_promo")],
        [InlineKeyboardButton(text="🗑 Удал. промокод", callback_data="admin_manage_promos"),
         InlineKeyboardButton(text="💵 Настройка цен", callback_data="admin_prices")],
        [InlineKeyboardButton(text="💎 Изменить пул", callback_data="admin_set_pool"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="admin_pool_stats")],
        [InlineKeyboardButton(text="🔄 Рестарт", callback_data="admin_restart")],
        [btn_back]
    ])

@dp.message(Command("admin"))
async def cmd_admin(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    await state.clear()
    text = "👑 <b>Панель администратора</b>\n\nВыберите нужный раздел:"
    await m.answer(text=text, reply_markup=get_admin_kb())

@dp.callback_query(F.data == "admin_menu")
async def admin_menu_callback(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text = "👑 <b>Панель администратора</b>\n\nВыберите нужный раздел:"
    try:
        await c.message.edit_text(text=text, reply_markup=get_admin_kb())
    except:
        await c.message.delete()
        await c.message.answer(text=text, reply_markup=get_admin_kb())
    await c.answer()

@dp.callback_query(F.data == "admin_restart")
async def admin_restart_btn(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    await c.answer()
    
    msg = await c.message.answer("🔄 Выполняется перезапуск...")
    with open("restart.tmp", "w", encoding="utf-8") as f:
        f.write(f"{time.time()}:{msg.message_id}")
        
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ================= ТОП ПОКУПАТЕЛЕЙ (ЛИДЕРБОРД) =================
@dp.callback_query(F.data == "admin_leaderboard")
async def show_leaderboard(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    
    users_names = {}
    if os.path.exists(ALL_USERS_FILE):
        with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    users_names[parts[0]] = parts[1]
                    
    stats = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) == 4:
                    uid, p_type, amt, _ = parts
                    if uid not in stats:
                        stats[uid] = {"stars": 0, "prem": 0}
                    if p_type == "stars":
                        stats[uid]["stars"] += int(amt)
                    elif p_type == "premium":
                        stats[uid]["prem"] += 1
                        
    sorted_users = sorted(stats.items(), key=lambda x: (x[1]["stars"], x[1]["prem"]), reverse=True)
    
    if not sorted_users:
        await c.answer("Покупок еще нет.", show_alert=True)
        return
        
    text = "🏆 <b>Топ покупателей:</b>\n\n"
    for i, (uid, data) in enumerate(sorted_users[:20], 1):
        uname = users_names.get(uid, "Без юзернейма")
        if uname and uname != "Без юзернейма" and not uname.startswith("@"):
            uname = "@" + uname
            
        stars = data["stars"]
        prem = data["prem"]
        
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(i, "👤")
        text += f"{medal} <b>{i}.</b> {uname} (<code>{uid}</code>)\n└ 💎 Звезд: {stars} | ⭐ Premium: {prem}\n\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except:
        pass
    await c.answer()

# ================= РЕДАКТИРОВАНИЕ ПУЛА И ЦЕН =================
@dp.callback_query(F.data == "admin_set_pool")
async def admin_set_pool_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID: return
    current_pool = get_global_pool()
    text = f"💎 <b>Изменение пула звезд</b>\n\nТекущий остаток: <b>{current_pool} ⭐️</b>\n\nВведите новое количество звезд в пуле (просто число):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]])
    await c.message.edit_text(text, reply_markup=kb)
    await state.set_state(AdminSteps.waiting_for_pool)
    await c.answer()

@dp.message(AdminSteps.waiting_for_pool)
async def admin_set_pool_process(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    if not m.text.isdigit():
        await m.answer("⚠️ Пожалуйста, введите только число.")
        return
    
    new_pool = int(m.text)
    set_global_pool(new_pool)
    await state.clear()
    await m.answer(f"✅ <b>Пул успешно обновлен!</b>\nНовый остаток: <b>{new_pool} ⭐️</b>", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "admin_prices")
async def admin_prices_menu(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    p = load_prices()
    presets = " ".join(map(str, p.get("star_presets", [50, 100, 250, 400, 500, 1000])))
    text = (
        "💵 <b>Управление ценами и товарами</b>\n\n"
        f"⭐️ <b>Звезды (за 1 шт):</b> {p['star_rub']} ₽ / {p['star_usdt']} $\n"
        f"🔢 <b>Кнопки звезд:</b> {presets}\n"
        f"⚡️ <b>Premium 3 мес:</b> {p['prem_3_rub']} ₽ / {p['prem_3_usdt']} $\n"
        f"⚡️ <b>Premium 6 мес:</b> {p['prem_6_rub']} ₽ / {p['prem_6_usdt']} $\n"
        f"⚡️ <b>Premium 1 год:</b> {p['prem_12_rub']} ₽ / {p['prem_12_usdt']} $\n\n"
        "Выберите, что хотите изменить:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Изменить цену Звезд", callback_data="edit_price_stars")],
        [InlineKeyboardButton(text="🔢 Изменить пресеты кнопок", callback_data="edit_star_presets")],
        [InlineKeyboardButton(text="⚡️ Изменить 3 мес", callback_data="edit_price_prem_3"),
         InlineKeyboardButton(text="⚡️ Изменить 6 мес", callback_data="edit_price_prem_6")],
        [InlineKeyboardButton(text="⚡️ Изменить 1 год", callback_data="edit_price_prem_12")],
        [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]
    ])
    await c.message.edit_text(text, reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "edit_star_presets")
async def edit_star_presets(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID: return
    p = load_prices()
    curr = " ".join(map(str, p.get("star_presets", [50, 100, 250, 400, 500, 1000])))
    text = f"🔢 <b>Настройка кнопок покупки звезд</b>\n\nТекущие значения: <code>{curr}</code>\n\nВведите новые значения через пробел (от 2 до 6 чисел):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_prices")]])
    await c.message.edit_text(text, reply_markup=kb)
    await state.set_state(AdminSteps.waiting_for_star_presets)
    await c.answer()

@dp.message(AdminSteps.waiting_for_star_presets)
async def process_star_presets(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.strip().split()
    presets = []
    for x in parts:
        if x.isdigit():
            presets.append(int(x))
    if not presets:
        await m.answer("⚠️ Вы не ввели ни одного числа.")
        return
    
    p = load_prices()
    p["star_presets"] = presets
    save_prices(p)
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К настройкам", callback_data="admin_prices")]])
    await m.answer(f"✅ <b>Кнопки звезд обновлены!</b>\nНовые значения: {presets}", reply_markup=kb)


@dp.callback_query(F.data.startswith("edit_price_"))
async def admin_edit_price_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID: return
    target = c.data.replace("edit_price_", "")
    await state.update_data(price_target=target)
    await state.set_state(AdminSteps.waiting_for_price)
    
    if target == "stars":
        text = "Введите новую цену за <b>1 звезду</b> в рублях (можно с копейками).\nПример: <code>1.52</code>"
    elif target == "prem_3":
        text = "Введите новую цену за <b>Premium 3 мес</b> в рублях.\nПример: <code>1250</code>"
    elif target == "prem_6":
        text = "Введите новую цену за <b>Premium 6 мес</b> в рублях.\nПример: <code>1700</code>"
    elif target == "prem_12":
        text = "Введите новую цену за <b>Premium 1 год</b> в рублях.\nПример: <code>2999</code>"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_prices")]])
    await c.message.edit_text(text, reply_markup=kb)
    await c.answer()

@dp.message(AdminSteps.waiting_for_price)
async def admin_edit_price_process(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    
    try:
        val_rub = float(m.text.replace(",", ".").strip())
    except ValueError:
        await m.answer("⚠️ Пожалуйста, введите только одно число (например, 1250 или 1.52).")
        return
        
    data = await state.get_data()
    target = data.get("price_target")
    
    p = load_prices()
    if target == "stars":
        ratio = p["star_usdt"] / p["star_rub"] if p["star_rub"] > 0 else 0.01
        p["star_rub"] = val_rub
        p["star_usdt"] = round(val_rub * ratio, 4)
    elif target == "prem_3":
        ratio = p["prem_3_usdt"] / p["prem_3_rub"] if p["prem_3_rub"] > 0 else 0.01
        p["prem_3_rub"] = int(val_rub)
        p["prem_3_usdt"] = round(val_rub * ratio, 2)
    elif target == "prem_6":
        ratio = p["prem_6_usdt"] / p["prem_6_rub"] if p["prem_6_rub"] > 0 else 0.01
        p["prem_6_rub"] = int(val_rub)
        p["prem_6_usdt"] = round(val_rub * ratio, 2)
    elif target == "prem_12":
        ratio = p["prem_12_usdt"] / p["prem_12_rub"] if p["prem_12_rub"] > 0 else 0.01
        p["prem_12_rub"] = int(val_rub)
        p["prem_12_usdt"] = round(val_rub * ratio, 2)
        
    save_prices(p)
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К настройкам цен", callback_data="admin_prices")]])
    await m.answer("✅ <b>Цена успешно обновлена!</b>\n<i>(Стоимость в USDT была автоматически пересчитана по текущему курсу)</i>", reply_markup=kb)


# ================= СПИСОК ПОЛЬЗОВАТЕЛЕЙ =================
@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
        
    if not os.path.exists(ALL_USERS_FILE):
        await c.answer("База пользователей пуста.", show_alert=True)
        return
        
    with open(ALL_USERS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        
    if not lines:
        await c.answer("База пользователей пуста.", show_alert=True)
        return
        
    text = f"👥 <b>Список пользователей (Всего: {len(lines)})</b>\n\n"
    file_text = f"Список пользователей (Всего: {len(lines)})\n\n"
    
    for i, line in enumerate(lines, 1):
        parts = line.split(":", 1)
        uname = parts[1] if len(parts) > 1 and parts[1] else "Без юзернейма"
        if uname != "Без юзернейма" and not uname.startswith("@"):
            uname = "@" + uname
        
        text += f"{i}. {uname}\n"
        file_text += f"{i}. {uname}\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]])
    
    if len(text) > 3500:
        file = BufferedInputFile(file_text.encode("utf-8"), filename="users_list.txt")
        await c.message.delete() 
        await c.message.answer_document(
            document=file, 
            caption=f"👥 <b>Всего пользователей: {len(lines)}</b>\n\n<i>Список слишком большой для сообщения, поэтому он отправлен файлом.</i>",
            reply_markup=kb
        )
    else:
        try:
            await c.message.edit_text(text, reply_markup=kb)
        except:
            await c.message.delete()
            await c.message.answer(text, reply_markup=kb)
            
    await c.answer()

# ================= РАССЫЛКА =================

@dp.callback_query(F.data == "admin_broadcast_start")
async def admin_broadcast_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
        
    text = (
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям бота.\n"
        "<i>Можно использовать текст, фото, видео или стикеры. Бот скопирует и отправит сообщение от своего лица.</i>"
    )
    await c.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]]))
    await state.set_state(AdminSteps.waiting_for_broadcast)
    await c.answer()

@dp.message(AdminSteps.waiting_for_broadcast)
async def process_broadcast(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
        
    await state.clear()
    
    users = get_all_user_ids()
    if not users:
        await m.answer("В базе нет пользователей для рассылки.", reply_markup=get_admin_kb())
        return

    status_msg = await m.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    for uid in users:
        try:
            await m.copy_to(chat_id=int(uid))
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await status_msg.edit_text(f"✅ <b>Рассылка успешно завершена!</b>\nДоставлено: {success} из {len(users)} пользователей.", reply_markup=get_admin_kb())

# ================= СОЗДАНИЕ ПРОМОКОДА =================

@dp.callback_query(F.data == "admin_add_promo")
async def admin_add_promo_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    
    text = "🎟 <b>Создание промокода (Шаг 1/4)</b>\n\nОтправьте в чат <b>название (слово)</b> для промокода:"
    msg = await c.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]]))
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(BuySteps.admin_promo_code)
    await c.answer()

@dp.message(BuySteps.admin_promo_code)
async def process_admin_promo_code(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    code = m.text.strip().upper()
    try:
        await m.delete()
    except:
        pass

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")

    await state.update_data(promo_code=code)
    await state.set_state(BuySteps.admin_promo_type)

    service_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Звезды", callback_data="promo_type_stars"),
         InlineKeyboardButton(text="⚡️ Telegram Premium", callback_data="promo_type_premium")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]
    ])

    text = f"🎟 <b>Создание промокода (Шаг 2/4)</b>\n\nСлово: <code>{code}</code>\n\nВыберите услугу для промокода:"
    if prompt_msg_id:
        try:
            await bot.edit_message_text(text=text, chat_id=m.chat.id, message_id=prompt_msg_id, reply_markup=service_kb)
            return
        except:
            pass
    await m.answer(text=text, reply_markup=service_kb)

@dp.callback_query(F.data.startswith("promo_type_"))
async def process_admin_promo_type(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return

    p_type = c.data.replace("promo_type_", "")
    await state.update_data(promo_type=p_type)
    await state.set_state(BuySteps.admin_promo_value)

    if p_type == "stars":
        val_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="50 звезд", callback_data="promo_val_50"),
             InlineKeyboardButton(text="100 звезд", callback_data="promo_val_100")],
            [InlineKeyboardButton(text="250 звезд", callback_data="promo_val_250"),
             InlineKeyboardButton(text="500 звезд", callback_data="promo_val_500")],
            [InlineKeyboardButton(text="1000 звезд", callback_data="promo_val_1000"),
             InlineKeyboardButton(text="5000 звезд", callback_data="promo_val_5000")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]
        ])
        text = "🎟 <b>Создание промокода (Шаг 3/4)</b>\n\nУслуга: <b>Звезды</b> ⭐️\nВыберите количество звезд, которое даст промокод:"
    else:
        val_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 месяц", callback_data="promo_val_1"),
             InlineKeyboardButton(text="3 месяца", callback_data="promo_val_3")],
            [InlineKeyboardButton(text="6 месяцев", callback_data="promo_val_6"),
             InlineKeyboardButton(text="12 месяцев", callback_data="promo_val_12")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]
        ])
        text = "🎟 <b>Создание промокода (Шаг 3/4)</b>\n\nУслуга: <b>Telegram Premium</b> ⚡️\nВыберите количество месяцев (дней) подписки:"

    await c.message.edit_text(text=text, reply_markup=val_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("promo_val_"))
async def process_admin_promo_val(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return

    val = int(c.data.replace("promo_val_", ""))
    await state.update_data(promo_value=val)
    await state.set_state(BuySteps.admin_promo_limit)

    limit_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 активация", callback_data="promo_limit_1"),
         InlineKeyboardButton(text="5 активаций", callback_data="promo_limit_5")],
        [InlineKeyboardButton(text="10 активаций", callback_data="promo_limit_10"),
         InlineKeyboardButton(text="♾ Бесконечно (inf)", callback_data="promo_limit_inf")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_menu")]
    ])

    text = f"🎟 <b>Создание промокода (Шаг 4/4)</b>\n\nНоминал: <b>{val}</b>\nУкажите лимит возможных активаций для всех пользователей:"
    await c.message.edit_text(text=text, reply_markup=limit_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("promo_limit_"))
async def process_admin_promo_limit(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return

    limit_val = c.data.replace("promo_limit_", "")
    data = await state.get_data()
    
    code = data.get("promo_code")
    p_type = data.get("promo_type")
    value = data.get("promo_value")

    add_promo_to_file(code, p_type, value, limit_val)
    await state.clear()

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_menu")]
    ])
    
    type_display = "Звезды ⭐️" if p_type == "stars" else "Telegram Premium ⚡️"
    
    text = (
        f"✅ <b>Промокод успешно создан и добавлен в базу!</b>\n\n"
        f"Слово: <code>{code}</code>\n"
        f"Услуга: <b>{type_display}</b>\n"
        f"Номинал/срок: <b>{value}</b>\n"
        f"Количество активаций: <b>{limit_val}</b>"
    )
    await c.message.edit_text(text=text, reply_markup=admin_kb)
    await c.answer()

@dp.callback_query(F.data == "admin_manage_promos")
async def admin_manage_promos(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    
    promos = load_promos()
    if not promos:
        text = "🗑 <b>Управление промокодами</b>\n\nВ базе пока нет активных промокодов."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]])
    else:
        text = "🗑 <b>Управление промокодами</b>\n\nНажмите на промокод, чтобы мгновенно удалить его:"
        buttons = []
        for code, info in promos.items():
            btn_text = f"❌ {code} ({info['type']}: {info['value']})"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"del_promo_{code}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await c.message.edit_text(text=text, reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data.startswith("del_promo_"))
async def delete_specific_promo(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    
    code_to_delete = c.data.replace("del_promo_", "")
    success = delete_promo_from_file(code_to_delete)

    if success:
        await c.answer(f"✅ Промокод {code_to_delete} удален!", show_alert=True)
    else:
        await c.answer(f"❌ Не удалось удалить промокод {code_to_delete}.", show_alert=True)

    promos = load_promos()
    if not promos:
        text = "🗑 <b>Управление промокодами</b>\n\nВ базе больше нет промокодов."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")]])
    else:
        text = "🗑 <b>Управление промокодами</b>\n\nНажмите на промокод, чтобы мгновенно удалить его:"
        buttons = []
        for code, info in promos.items():
            btn_text = f"❌ {code} ({info['type']}: {info['value']})"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"del_promo_{code}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await c.message.edit_text(text=text, reply_markup=kb)

@dp.callback_query(F.data == "admin_pool_stats")
async def admin_pool_stats(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    
    current_pool = get_global_pool()
    promos = load_promos()
    promo_count = len(promos)

    text = (
        f"📊 <b>Статистика системы:</b>\n\n"
        f"• Звезд в общем пуле: <b>{current_pool} ⭐️</b>\n"
        f"• Активных промокодов в базе: <b>{promo_count} шт.</b>"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_menu")]
    ])
    await c.message.edit_text(text=text, reply_markup=admin_kb)
    await c.answer()


# ================= ПРОФИЛЬ И ИСТОРИЯ ПОКУПОК =================

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(c: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "👋 <b>Главное меню:</b>\n\n"
        "Выберите нужное действие ниже 👇"
    )
    await c.message.edit_text(text=text, reply_markup=main_kb)
    await c.answer()

@dp.callback_query(F.data == "profile")
async def profile_menu(c: CallbackQuery):
    user = c.from_user
    stats = get_user_stats(user.id)
    
    text = (
        f"👤 <b>Ваш профиль:</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Имя: {user.full_name}\n\n"
        f"📊 <b>Статистика покупок:</b>\n"
        f"• Всего куплено звезд: <b>{stats['stars']} ⭐️</b>\n"
        f"• Куплено подписок Premium: <b>{stats['prem_count']} шт.</b>"
    )
    
    profile_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История покупок", callback_data="history_menu")],
        [btn_back]
    ])
    await c.message.edit_text(text=text, reply_markup=profile_kb)
    await c.answer()

@dp.callback_query(F.data == "history_menu")
async def history_menu(c: CallbackQuery):
    text = "📜 <b>История покупок</b>\n\nВыберите категорию для просмотра:"
    history_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Звезды", callback_data="history_stars")],
        [InlineKeyboardButton(text="⭐ Telegram Premium", callback_data="history_prem")],
        [btn_back_profile]
    ])
    await c.message.edit_text(text=text, reply_markup=history_kb)
    await c.answer()

@dp.callback_query(F.data == "history_stars")
async def history_stars(c: CallbackQuery):
    stats = get_user_stats(c.from_user.id)
    items = "\n\n".join(stats["stars_history"]) if stats["stars_history"] else "<i>У вас пока нет купленных звезд</i>"
    text = f"💎 <b>История покупок: Звезды</b>\n\n{items}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к истории", callback_data="history_menu")]])
    await c.message.edit_text(text=text, reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "history_prem")
async def history_prem(c: CallbackQuery):
    stats = get_user_stats(c.from_user.id)
    items = "\n\n".join(stats["prem_history"]) if stats["prem_history"] else "<i>У вас пока нет купленных подписок Premium</i>"
    text = f"⭐ <b>История покупок: Telegram Premium</b>\n\n{items}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад к истории", callback_data="history_menu")]])
    await c.message.edit_text(text=text, reply_markup=kb)
    await c.answer()

# ================= СИСТЕМА ПРОМОКОДОВ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ =================

@dp.callback_query(F.data == "use_promo")
async def promo_start(c: CallbackQuery, state: FSMContext):
    text = "🎟 <b>Введите ваш промокод в чат:</b>\n\n<i>Отправьте текстовое сообщение с кодом</i>"
    msg = await c.message.edit_text(text=text, reply_markup=cancel_kb)
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(BuySteps.waiting_for_promo)
    await c.answer()

@dp.message(BuySteps.waiting_for_promo)
async def process_promo(m: types.Message, state: FSMContext):
    user_msg_id = m.message_id
    chat_id = m.chat.id
    code = m.text.strip().upper()

    try:
        await bot.delete_message(chat_id=chat_id, message_id=user_msg_id)
    except:
        pass

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")

    promo_codes = load_promos()

    if code in promo_codes:
        await state.clear()
        promo = promo_codes[code]
        p_type = promo["type"]
        val = promo["value"]
        limit = promo["limit"]

        user = m.from_user
        user_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a> (@{user.username or 'нет_юзернейма'})"

        if isinstance(limit, int) and limit <= 0:
            response_text = "❌ <b>Лимит активаций этого промокода исчерпан.</b>"
            target_kb = cancel_kb
        else:
            remaining = update_promo_file_after_use(code)
            limit_info = f"\n🔄 <b>Осталось активаций:</b> {remaining}" if isinstance(remaining, int) and remaining >= 0 else ""

            if p_type == "stars":
                current_pool = get_global_pool()
                if val <= current_pool:
                    set_global_pool(current_pool - val)
                    save_user_purchase(user.id, "stars", val, "Себе (Промокод)")
                    response_text = f"🎉 <b>Промокод успешно активирован!</b>\n\nВам начислено: <b>{val} ⭐️</b>{limit_info}"
                    if ADMIN_ID != 0:
                        await bot.send_message(ADMIN_ID, f"🎟 <b>Активирован промокод на звезды!</b>\n\n👤 Пользователь: {user_link}\n💎 Награда: {val} ⭐️{limit_info}")
                else:
                    response_text = "⚠️ К сожалению, в пуле пока нет такого количества звезд."
            elif p_type == "premium":
                save_user_purchase(user.id, "premium", val, "Себе (Промокод)")
                response_text = f"🎉 <b>Промокод на Telegram Premium ({val} мес.) успешно активирован!</b>\n\nЗаявка отправлена администратору.{limit_info}"
                if ADMIN_ID != 0:
                    await bot.send_message(ADMIN_ID, f"🔔 <b>Активирован промокод на Premium!</b>\n\n👤 Покупатель: {user_link}\n🌟 Товар: Telegram Premium ({val} мес.){limit_info}")
            else:
                response_text = f"🎉 <b>Промокод активирован!</b> Скидка: {val}%."

            target_kb = main_kb
    else:
        response_text = "❌ <b>Неверный промокод</b> или срок его действия истек.\n\n🎟 <i>Попробуйте ввести другой промокод или нажмите «Отмена»:</i>"
        target_kb = cancel_kb

    if prompt_msg_id:
        try:
            await bot.edit_message_text(text=response_text, chat_id=chat_id, message_id=prompt_msg_id, reply_markup=target_kb)
            return
        except:
            pass

    await m.answer(text=response_text, reply_markup=target_kb)

# ================= ПОКУПКА ЗВЕЗД =================

@dp.callback_query(F.data == "buy_stars")
async def start_buy(c: CallbackQuery, state: FSMContext):
    current_pool = get_global_pool()
    text = (
        f"💎 <b>Доступно в остатке:</b> {current_pool} ⭐️\n\n"
        "Выберите нужное количество из списка ниже:"
    )
    
    msg = await c.message.edit_text(text=text, reply_markup=get_stars_kb())
    await state.update_data(prompt_msg_id=msg.message_id)
    await state.set_state(BuySteps.waiting_for_amount)
    await c.answer()

@dp.callback_query(F.data == "custom_amount")
async def process_custom_amount(c: CallbackQuery, state: FSMContext):
    text = "✍️ <b>Введите желаемое количество звезд для покупки (от 50 до 10000):</b>"
    msg = await c.message.edit_text(text=text, reply_markup=cancel_kb)
    await state.update_data(prompt_msg_id=msg.message_id)
    await c.answer()

@dp.callback_query(F.data.startswith("preset_"))
async def process_preset(c: CallbackQuery, state: FSMContext):
    amt = int(c.data.split("_")[1])
    current_pool = get_global_pool()

    if amt > current_pool:
        await c.answer("⚠️ Недостаточно звезд в остатке!", show_alert=True)
        return

    await state.clear()
    
    recipient_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Себе", callback_data=f"stars_rec_self_{amt}")],
        [InlineKeyboardButton(text="👥 Другому человеку", callback_data=f"stars_rec_other_{amt}")],
        [btn_back]
    ])
    
    text = f"Вы выбрали: <b>{amt} ⭐️</b>\n\nКого указать получателем?"
    await c.message.edit_text(text=text, reply_markup=recipient_kb)
    await c.answer()

@dp.message(BuySteps.waiting_for_amount)
async def proc_amt(m: types.Message, state: FSMContext):
    user_msg_id = m.message_id
    chat_id = m.chat.id

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")

    try:
        await bot.delete_message(chat_id=chat_id, message_id=user_msg_id)
    except:
        pass

    if not m.text.isdigit():
        return

    amt = int(m.text)
    current_pool = get_global_pool()

    if amt < 50 or amt > 10000:
        return

    if amt > current_pool:
        return

    await state.clear()
    
    recipient_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Себе", callback_data=f"stars_rec_self_{amt}")],
        [InlineKeyboardButton(text="👥 Другому человеку", callback_data=f"stars_rec_other_{amt}")],
        [btn_back]
    ])

    text = f"Вы выбрали: <b>{amt} ⭐️</b>\n\nКого указать получателем?"
    
    if prompt_msg_id:
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=prompt_msg_id, reply_markup=recipient_kb)
            return
        except:
            pass

    await m.answer(text=text, reply_markup=recipient_kb)

@dp.callback_query(F.data.startswith("stars_rec_self_"))
async def stars_rec_self(c: CallbackQuery):
    amt = int(c.data.split("_")[3])
    await show_stars_payment_methods(c=c, amt=amt, recipient="Себе")

@dp.callback_query(F.data.startswith("stars_rec_other_"))
async def stars_rec_other(c: CallbackQuery, state: FSMContext):
    amt = int(c.data.split("_")[3])
    text = "✍️ <b>Введите Telegram юзернейм получателя (можно без @):</b>"
    msg = await c.message.edit_text(text=text, reply_markup=cancel_kb)
    await state.update_data(prompt_msg_id=msg.message_id, pending_amt=amt)
    await state.set_state(BuySteps.waiting_for_recipient_stars)
    await c.answer()

@dp.message(BuySteps.waiting_for_recipient_stars)
async def proc_recipient_stars(m: types.Message, state: FSMContext):
    recipient = m.text.strip().replace("t.me/", "").replace("https://", "")
    if not recipient.startswith("@"):
        recipient = "@" + recipient
        
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    amt = data.get("pending_amt")

    try:
        await bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
    except:
        pass

    await state.clear()
    await show_stars_payment_methods(c=None, amt=amt, recipient=recipient, m=m, prompt_msg_id=prompt_msg_id)

async def show_stars_payment_methods(c: CallbackQuery = None, amt: int = 0, recipient: str = "", m: types.Message = None, prompt_msg_id: int = None):
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💲 Оплатить в Tether (USDT)", callback_data=f"pay_usdt_{amt}_{recipient}")],
        [InlineKeyboardButton(text="💳 Оплатить картой (РФ)", callback_data=f"pay_card_{amt}_{recipient}")],
        [InlineKeyboardButton(text="📱 Оплатить по СБП", callback_data="pay_sbp")],
        [btn_back]
    ])

    text = f"Вы выбрали: <b>{amt} ⭐️</b>\nПолучатель: <b>{recipient}</b>\n\nВыберите способ оплаты:"
    
    if c:
        await c.message.edit_text(text=text, reply_markup=pay_kb)
        await c.answer()
    else:
        if prompt_msg_id:
            try:
                await bot.edit_message_text(text=text, chat_id=m.chat.id, message_id=prompt_msg_id, reply_markup=pay_kb)
                return
            except:
                pass
        await m.answer(text=text, reply_markup=pay_kb)

@dp.callback_query(F.data == "pay_sbp")
async def pay_sbp_alert(c: CallbackQuery):
    await c.answer("⚠️ Сервис оплаты по СБП находится в разработке. Пожалуйста, воспользуйтесь оплатой картой.", show_alert=True)

@dp.callback_query(F.data.startswith("pay_usdt_"))
async def pay_usdt(c: CallbackQuery):
    parts = c.data.split("_", 3)
    amt = int(parts[2])
    recipient = parts[3]
    
    p = load_prices()
    price_usdt = round(amt * p["star_usdt"], 2)
    if price_usdt < 0.01:
        price_usdt = 0.01

    await c.message.edit_text(f"⏳ Создаю счет на <b>{amt} ⭐️</b> в Tether (USDT)...")

    try:
        invoice = await crypto.create_invoice(
            asset='USDT',
            amount=price_usdt,
            description=f"Покупка {amt} Telegram Stars",
            payload=f"stars_{amt}"
        )

        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {price_usdt} USDT", url=invoice.bot_invoice_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_usdt_{invoice.invoice_id}_{amt}_{recipient}")],
            [btn_back]
        ])

        text = f"✅ Счет в Tether (USDT) создан!\n\nТовар: <b>{amt} ⭐️</b>\nПолучатель: <b>{recipient}</b>\nСумма: <b>{price_usdt} USDT</b>\n\nПосле перевода нажмите кнопку проверки ниже:"
        await c.message.edit_text(text=text, reply_markup=pay_kb)
    except Exception as e:
        logging.error(f"Ошибка создания счета CryptoBot: {e}")
        await c.message.edit_text("⚠️ Ошибка при создании счета оплаты. Попробуйте позже.", reply_markup=main_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("check_usdt_"))
async def check_usdt_stars_payment(c: CallbackQuery):
    parts = c.data.split("_", 4)
    invoice_id = int(parts[2])
    amt = int(parts[3])
    recipient = parts[4]

    try:
        invoice = await crypto.get_invoice(invoice_id=invoice_id)
        if invoice:
            if invoice.status == "paid":
                current_pool = get_global_pool()
                new_pool = max(0, current_pool - amt)
                set_global_pool(new_pool)

                save_user_purchase(c.from_user.id, "stars", amt, recipient)

                text = f"🎉 <b>Оплата Tether получена!</b>\n\nВы купили: <b>{amt} ⭐️</b>\nПолучатель: <b>{recipient}</b>\n📊 Остаток пула: <b>{new_pool} ⭐️</b>\n\nСпасибо за покупку!"
                await c.message.edit_text(text=text, reply_markup=main_kb)
            else:
                await c.answer("⏳ Оплата еще не поступила. Попробуйте чуть позже.", show_alert=True)
        else:
            await c.answer("⚠️ Счет не найден.", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка проверки счета: {e}")
        await c.answer("⚠️ Ошибка при проверке статуса.", show_alert=True)

@dp.callback_query(F.data.startswith("pay_card_"))
async def pay_card(c: CallbackQuery):
    parts = c.data.split("_", 3)
    amt = int(parts[2])
    recipient = parts[3]
    
    p = load_prices()
    price_rub = math.ceil(amt * p["star_rub"])
    
    card_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_card_stars_{amt}_{recipient}")],
        [InlineKeyboardButton(text="💬 Поддержка (Отправить чек)", url="https://t.me/tamaevlox1")],
        [btn_back]
    ])

    text = (
        "🇷🇺 <b>Оплата переводом на карту</b>\n\n"
        f"Товар: <b>{amt} ⭐️</b>\n"
        f"Получатель: <b>{recipient}</b>\n"
        f"Сумма к оплате: <b>{price_rub} RUB</b>\n\n"
        "💳 <b>Реквизиты для перевода:</b>\n"
        "• Банк: <b>Ozon Bank (Озон Банк)</b>\n"
        "• Номер карты: <code>2204321286658695</code>\n\n"
        "📌 <i>После перевода нажмите кнопку «Проверить оплату» и отправьте чек в поддержку.</i>\n\n"
        "⚠️ <b>Примечание:</b> При переводе может взиматься комиссия вашего банка."
    )
    
    await c.message.edit_text(text=text, reply_markup=card_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("check_card_stars_"))
async def check_card_stars(c: CallbackQuery):
    parts = c.data.split("_", 4)
    amt = parts[3]
    recipient = parts[4]
    user = c.from_user
    user_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a> (@{user.username or 'нет_юзернейма'})"

    if ADMIN_ID != 0:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_yes_stars_{user.id}_{amt}_{recipient}"),
             InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_no_stars_{user.id}_{amt}_{recipient}")]
        ])
        
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 <b>Новая заявка на оплату (Карта)!</b>\n\n👤 Покупатель: {user_link}\n🎁 Получатель: <b>{recipient}</b>\n💎 Товар: <b>{amt} ⭐️ Звезд</b>",
                reply_markup=admin_kb
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу: {e}")

    done_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Заявка отправлена на проверку", callback_data="already_sent")],
        [InlineKeyboardButton(text="💬 Поддержка (Отправить чек)", url="https://t.me/tamaevlox1")],
        [btn_back]
    ])
    try:
        await c.message.edit_reply_markup(reply_markup=done_kb)
    except:
        pass

    await c.answer("⏳ Платеж успешно отправлен на проверку администратору!", show_alert=True)

@dp.callback_query(F.data == "already_sent")
async def already_sent_alert(c: CallbackQuery):
    await c.answer("⏳ Ваша заявка уже находится на проверке у администратора. Ожидайте ответа!", show_alert=True)


# ================= ПОКУПКА PREMIUM =================

@dp.callback_query(F.data == "buy_premium")
async def p_menu(c: CallbackQuery):
    t = "🌟 <b>Выбор подписки Telegram Premium</b>\n\nВыберите срок:"
    await c.message.edit_text(text=t, reply_markup=get_prem_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def p_proc(c: CallbackQuery, state: FSMContext):
    mo = int(c.data.split("_")[1])
    
    recipient_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Себе", callback_data=f"prem_rec_self_{mo}")],
        [InlineKeyboardButton(text="👥 Другому человеку", callback_data=f"prem_rec_other_{mo}")],
        [btn_back]
    ])
    
    text = f"Вы выбрали: <b>Telegram Premium ({mo} мес.)</b>\n\nКого указать получателем?"
    await c.message.edit_text(text=text, reply_markup=recipient_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("prem_rec_self_"))
async def prem_rec_self(c: CallbackQuery):
    mo = int(c.data.split("_")[3])
    await show_prem_payment_methods(c=c, mo=mo, recipient="Себе")

@dp.callback_query(F.data.startswith("prem_rec_other_"))
async def prem_rec_other(c: CallbackQuery, state: FSMContext):
    mo = int(c.data.split("_")[3])
    text = "✍️ <b>Введите Telegram юзернейм получателя (можно без @):</b>"
    msg = await c.message.edit_text(text=text, reply_markup=cancel_kb)
    await state.update_data(prompt_msg_id=msg.message_id, pending_mo=mo)
    await state.set_state(BuySteps.waiting_for_recipient_prem)
    await c.answer()

@dp.message(BuySteps.waiting_for_recipient_prem)
async def proc_recipient_prem(m: types.Message, state: FSMContext):
    recipient = m.text.strip().replace("t.me/", "").replace("https://", "")
    if not recipient.startswith("@"):
        recipient = "@" + recipient
        
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    mo = data.get("pending_mo")

    try:
        await bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
    except:
        pass

    await state.clear()
    await show_prem_payment_methods(c=None, mo=mo, recipient=recipient, m=m, prompt_msg_id=prompt_msg_id)

async def show_prem_payment_methods(c: CallbackQuery = None, mo: int = 0, recipient: str = "", m: types.Message = None, prompt_msg_id: int = None):
    p = load_prices()
    
    if mo == 3:
        p_rub, p_usdt = p["prem_3_rub"], p["prem_3_usdt"]
    elif mo == 6:
        p_rub, p_usdt = p["prem_6_rub"], p["prem_6_usdt"]
    else:
        p_rub, p_usdt = p["prem_12_rub"], p["prem_12_usdt"]

    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💲 Оплатить в Tether ({p_usdt} USDT)", callback_data=f"pay_prem_usdt_{p_usdt}_{mo}_{recipient}")],
        [InlineKeyboardButton(text=f"💳 Оплатить картой ({p_rub} ₽)", callback_data=f"pay_prem_card_{p_rub}_{mo}_{recipient}")],
        [InlineKeyboardButton(text="📱 Оплатить по СБП", callback_data="pay_sbp")],
        [btn_back]
    ])
    
    text = f"Вы выбрали: <b>Telegram Premium ({mo} мес.)</b>\nПолучатель: <b>{recipient}</b>\n\nВыберите способ оплаты:"
    
    if c:
        await c.message.edit_text(text=text, reply_markup=pay_kb)
        await c.answer()
    else:
        if prompt_msg_id:
            try:
                await bot.edit_message_text(text=text, chat_id=m.chat.id, message_id=prompt_msg_id, reply_markup=pay_kb)
                return
            except:
                pass
        await m.answer(text=text, reply_markup=pay_kb)

@dp.callback_query(F.data.startswith("pay_prem_usdt_"))
async def pay_prem_usdt(c: CallbackQuery):
    parts = c.data.split("_", 4)
    price_usdt = float(parts[3])
    mo = int(parts[4])
    recipient = parts[5]

    await c.message.edit_text(f"⏳ Создаю счет на Premium ({mo} мес.) в Tether (USDT)...")

    try:
        invoice = await crypto.create_invoice(
            asset='USDT',
            amount=price_usdt,
            description=f"Telegram Premium {mo} мес.",
            payload=f"prem_{mo}"
        )

        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {price_usdt} USDT", url=invoice.bot_invoice_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_prem_{invoice.invoice_id}_{mo}_{recipient}")],
            [btn_back]
        ])

        text = f"✅ Счет в Tether (USDT) создан!\n\nТовар: <b>Premium ({mo} мес.)</b>\nПолучатель: <b>{recipient}</b>\nСумма: <b>{price_usdt} USDT</b>\n\nПосле перевода нажмите кнопку проверки ниже:"
        await c.message.edit_text(text=text, reply_markup=pay_kb)
    except Exception as e:
        logging.error(f"Ошибка создания счета CryptoBot: {e}")
        await c.message.edit_text("⚠️ Ошибка при создании счета оплаты. Попробуйте позже.", reply_markup=main_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("check_prem_"))
async def check_prem_payment(c: CallbackQuery):
    parts = c.data.split("_", 4)
    invoice_id = int(parts[2])
    mo = int(parts[3])
    recipient = parts[4]

    try:
        invoice = await crypto.get_invoice(invoice_id=invoice_id)
        if invoice:
            if invoice.status == "paid":
                save_user_purchase(c.from_user.id, "premium", mo, recipient)
                text = f"🎉 <b>Оплата Tether получена!</b>\n\nВы купили: <b>Premium ({mo} мес.)</b>\nПолучатель: <b>{recipient}</b>\n\nПодписка выдается в течение 2 минут."
                await c.message.edit_text(text=text, reply_markup=main_kb)
            else:
                await c.answer("⏳ Оплата еще не поступила. Попробуйте чуть позже.", show_alert=True)
        else:
            await c.answer("⚠️ Счет не найден.", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка проверки счета: {e}")
        await c.answer("⚠️ Ошибка при проверке статуса.", show_alert=True)

@dp.callback_query(F.data.startswith("pay_prem_card_"))
async def pay_prem_card(c: CallbackQuery):
    parts = c.data.split("_", 4)
    price_rub = int(parts[3])
    mo = int(parts[4])
    recipient = parts[5]
    
    card_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_card_prem_{mo}_{recipient}")],
        [InlineKeyboardButton(text="💬 Поддержка (Отправить чек)", url="https://t.me/tamaevlox1")],
        [btn_back]
    ])

    text = (
        "🇷🇺 <b>Оплата переводом на карту</b>\n\n"
        f"Товар: <b>Telegram Premium ({mo} мес.)</b>\n"
        f"Получатель: <b>{recipient}</b>\n"
        f"Сумма к оплате: <b>{price_rub} RUB</b>\n\n"
        "💳 <b>Реквизиты для перевода:</b>\n"
        "• Банк: <b>Ozon Bank (Озон Банк)</b>\n"
        "• Номер карты: <code>2204321286658695</code>\n\n"
        "📌 <i>После перевода нажмите кнопку «Проверить оплату» и отправьте чек в поддержку.</i>\n\n"
        "⚠️ <b>Примечание:</b> При переводе может взиматься комиссия вашего банка."
    )
    
    await c.message.edit_text(text=text, reply_markup=card_kb)
    await c.answer()

@dp.callback_query(F.data.startswith("check_card_prem_"))
async def check_card_prem(c: CallbackQuery):
    parts = c.data.split("_", 4)
    mo = parts[3]
    recipient = parts[4]
    user = c.from_user
    user_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a> (@{user.username or 'нет_юзернейма'})"

    if ADMIN_ID != 0:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_yes_prem_{user.id}_{mo}_{recipient}"),
             InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_no_prem_{user.id}_{mo}_{recipient}")]
        ])
        
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 <b>Новая заявка на Premium (Карта)!</b>\n\n👤 Покупатель: {user_link}\n🎁 Получатель: <b>{recipient}</b>\n🌟 Товар: <b>Telegram Premium ({mo} мес.)</b>",
                reply_markup=admin_kb
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу: {e}")

    done_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Заявка отправлена на проверку", callback_data="already_sent")],
        [InlineKeyboardButton(text="💬 Поддержка (Отправить чек)", url="https://t.me/tamaevlox1")],
        [btn_back]
    ])
    try:
        await c.message.edit_reply_markup(reply_markup=done_kb)
    except:
        pass

    await c.answer("⏳ Платеж успешно отправлен на проверку администратору!", show_alert=True)


# ================= АДМИНСКИЕ КНОПКИ (ПОДТВЕРЖДЕНИЕ С КОММЕНТАРИЕМ) =================

async def execute_admin_action(bot: Bot, state: FSMContext, comment: str = None):
    data = await state.get_data()
    action_data = data.get("admin_action")
    orig_msg_id = data.get("msg_id")
    
    if not action_data:
        return
        
    parts = action_data.split("_", 5)
    
    target_type = parts[2]
    user_id = int(parts[3])
    amount_or_mo = parts[4]
    recipient = parts[5] if len(parts) > 5 else "Себе"
    
    comment_text = f"\n\n💬 <b>Комментарий администратора:</b> <i>{comment}</i>" if comment else ""
    
    try:
        if action_data.startswith("adm_yes_"):
            if target_type == "stars":
                amt = int(amount_or_mo)
                current_pool = get_global_pool()
                set_global_pool(max(0, current_pool - amt))
                save_user_purchase(user_id, "stars", amt, recipient)
                
                await bot.send_message(user_id, f"🎉 <b>Оплата подтверждена!</b>\n\nЗаказ для <b>{recipient}</b> на <b>{amt} ⭐️</b> выдан. Спасибо за покупку! 🚀{comment_text}")
            else:
                mo = amount_or_mo
                save_user_purchase(user_id, "premium", int(mo), recipient)
                await bot.send_message(user_id, f"🎉 <b>Оплата подтверждена!</b>\n\nПодписка <b>Telegram Premium ({mo} мес.)</b> для <b>{recipient}</b> успешно активирована! 🚀{comment_text}")
                
            await bot.edit_message_text(chat_id=ADMIN_ID, message_id=orig_msg_id, text="<b>✅ СТАТУС: Одобрено</b>" + comment_text)
                
        elif action_data.startswith("adm_no_"):
            await bot.send_message(user_id, f"❌ <b>Оплата не найдена или отклонена администратором.</b>\nЕсли вы совершили перевод, пожалуйста, обратитесь в поддержку: @tamaevlox1{comment_text}")
            await bot.edit_message_text(chat_id=ADMIN_ID, message_id=orig_msg_id, text="<b>❌ СТАТУС: Отклонено</b>" + comment_text)
            
    except Exception as e:
        logging.error(f"Ошибка при обработке заказа: {e}")

    await state.clear()

@dp.callback_query(F.data.startswith("adm_yes_") | F.data.startswith("adm_no_"))
async def adm_action_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
        
    await state.update_data(admin_action=c.data, msg_id=c.message.message_id)
    await state.set_state(AdminSteps.waiting_for_comment)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏩ Пропустить (без комментария)", callback_data="admin_skip_comment")]])
    await c.message.answer("✍️ <b>Напишите комментарий</b> для покупателя (до 50 слов) или пропустите этот шаг:", reply_markup=kb)
    await c.answer()

@dp.message(AdminSteps.waiting_for_comment)
async def admin_comment_received(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
        
    words = m.text.split()
    if len(words) > 50:
        await m.answer("⚠️ Комментарий слишком длинный! Пожалуйста, уложитесь в 50 слов.")
        return
        
    await execute_admin_action(bot, state, m.text)
    await m.answer("✅ Действие выполнено, вердикт и комментарий отправлены покупателю.")

@dp.callback_query(F.data == "admin_skip_comment")
async def admin_skip_comment(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await execute_admin_action(bot, state, None)
    await c.message.edit_text("✅ Действие выполнено без комментария.")
    await c.answer()

@dp.pre_checkout_query()
async def pre_chk(pcq: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pcq.id, ok=True)

@dp.callback_query(F.data == "cancel")
async def c_buy(c: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await c.message.delete()
    except:
        pass
    
    text = (
        "👋 Действие отменено.\n\n"
        "🕒 <b>График работы (выдача/поддержка):</b> с 09:00 до 00:00\n\n"
        "Выберите действие 👇"
    )
    await c.message.answer(text=text, reply_markup=main_kb)
    await c.answer()

@dp.callback_query(F.data == "help")
async def h_btn(c: CallbackQuery):
    t = "⚠️ По всем вопросам обращайтесь в поддержку: @tamaevlox1"
    await c.message.answer(t)
    await c.answer()

@dp.callback_query(F.data == "about")
async def a_btn(c: CallbackQuery):
    t = "🤖 Бот для покупки Telegram Stars и Premium (Tether/Карта РФ/СБП/Звезды)."
    await c.message.answer(t)
    await c.answer()

async def main():
    default_commands = [
        BotCommand(command="start", description="Запустить/Перезапустить бота")
    ]
    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())
    
    admin_commands = [
        BotCommand(command="start", description="Запустить/Перезапустить бота"),
        BotCommand(command="admin", description="Панель администратора")
    ]
    try:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID))
    except Exception as e:
        logging.error(f"Не удалось установить команды для админа: {e}")
        
    while True:
        try:
            print("🤖 Бот успешно запущен!")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"⚠️ Ошибка в работе бота: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
