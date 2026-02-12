from config import * 
import asyncio
import logging
import random
import sqlite3
import time
from datetime import datetime
import os
import subprocess
import socks
import socket
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# ================= ПРОКСИ =================

TOR_PATH = os.path.join("tor/", "tor.exe")
TORRC_PATH = os.path.join("tor/", "torrc")

def tor_is_running():
    try:
        s = socket.create_connection(("127.0.0.1", 9050), timeout=2)
        s.close()
        return True
    except:
        return False

def start_tor():
    try:
        if tor_is_running():
            print("Tor already running")
            return

        print("Starting Tor...")
        process = subprocess.Popen(
            [TOR_PATH, "-f", TORRC_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        
        if stdout:
            print(stdout.decode())
        if stderr:
            print(stderr.decode())

        for i in range(30):
            if tor_is_running():
                print("Tor started")
                return process  # Возвращаем объект процесса Tor
            time.sleep(1)

        raise RuntimeError("Tor failed to start")
    except Exception as e:
        logging.error(f"Ошибка при запуске Tor: {e}")
        raise

def stop_tor(process):
    try:
        process.terminate()  # Останавливаем Tor процесс
        print("Tor stopped successfully.")
    except Exception as e:
        logging.error(f"Ошибка при остановке Tor: {e}")

# ================= VK API =================

async def vk(method, params):
    params["access_token"] = VK_TOKEN
    params["v"] = "5.131"
    
    for attempt in range(5):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.vk.com/method/{method}",
                    params=params,
                    timeout=10
                )
            return response.json()
        except httpx.RequestError as e:
            logging.error(f"Ошибка при запросе VK API: {e}")
            if attempt < 4:
                await asyncio.sleep(5)  # Задержка перед повтором
            else:
                raise

async def get_posts():
    response = await vk("wall.get", {"owner_id": GROUP_ID, "count": 5})
    return response["response"]["items"]

async def like(pid):
    await vk("likes.add", {
        "type": "post",
        "owner_id": GROUP_ID,
        "item_id": pid
    })

async def repost(pid):
    await vk("wall.repost", {
        "object": f"wall{GROUP_ID}_{pid}"
    })

async def comment(pid, text):
    await vk("wall.createComment", {
        "owner_id": GROUP_ID,
        "post_id": pid,
        "message": text
    })

# ================= БАЗА =================

def is_done(pid):
    with sqlite3.connect("processed_posts.db") as db:
        cur = db.cursor()
        cur.execute("SELECT id FROM posts WHERE id=?", (pid,))
        return cur.fetchone()

def mark_done(pid):
    with sqlite3.connect("processed_posts.db") as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO posts VALUES (?,?)",
            (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        db.commit()

# ================= КОММЕНТАРИИ =================

def load_comments():
    try:
        with open(COMMENTS_FILE, encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]
    except:
        return []

def save_comments(data):
    with open(COMMENTS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(data))

# ================= КЛАВИАТУРЫ =================

def main_keyboard():
    return InlineKeyboardMarkup([  
        [InlineKeyboardButton("▶ Запустить бота", callback_data="start")],
        [InlineKeyboardButton("⏹ Остановить бота", callback_data="stop")],
        [InlineKeyboardButton("🔁 Перезапустить бота", callback_data="restart")],
        [InlineKeyboardButton("💬 Комментарии", callback_data="comments")]
    ])

def comments_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить", callback_data="add")],
        [InlineKeyboardButton("📝 Редактировать", callback_data="edit")],
        [InlineKeyboardButton("🗑 Удалить", callback_data="del")],
        [InlineKeyboardButton("⬅ Назад", callback_data="back")]
    ])

def cancel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ])

# ================= VK WORKER =================

async def vk_worker(app):
    await app.bot.send_message(USER_ID, "Бот запущен!")
    global bot_running

    while True:
        if bot_running:
            try:
                posts = await get_posts()
                comments = load_comments()

                if not comments:
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                for p in posts:
                    pid = p["id"]
                    if not is_done(pid):
                        c = random.choice(comments)

                        await like(pid)
                        await repost(pid)
                        await comment(pid, c)
                        mark_done(pid)

                        logging.info(f"Отправка уведомления о новом посте: {pid}")
                        await app.bot.send_message(
                            USER_ID,
                            f"""✅ Обработан пост
ID: {pid}
Время: {datetime.now()}
Комментарий: {c}"""
                        )
            except Exception as e:
                logging.error(f"Ошибка в vk_worker: {e}")
                # Перезапуск работы бота в случае ошибки
                await asyncio.sleep(5)  # Пауза перед переподключением

        await asyncio.sleep(CHECK_INTERVAL)

# ================= BUTTONS =================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_running
    q = update.callback_query
    await q.answer()

    if q.data == "start":
        bot_running = True
        await q.message.reply_text("Бот запущен", reply_markup=main_keyboard())

    elif q.data == "stop":
        bot_running = False
        await q.message.reply_text("Бот остановлен", reply_markup=main_keyboard())

    elif q.data == "restart":
        bot_running = False
        await asyncio.sleep(2)
        bot_running = True
        await q.message.reply_text("Бот перезапущен", reply_markup=main_keyboard())

    elif q.data == "comments":
        await q.message.reply_text("Меню комментариев:", reply_markup=comments_keyboard())

    elif q.data == "add":
        context.user_data["mode"] = "add"
        await q.message.reply_text("Введите комментарий:", reply_markup=cancel_keyboard())

    elif q.data == "edit":
        lst = load_comments()
        text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(lst))
        context.user_data["mode"] = "edit"
        await q.message.reply_text("Номер и новый текст:\n\n" + text, reply_markup=cancel_keyboard())

    elif q.data == "del":
        lst = load_comments()
        text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(lst))
        context.user_data["mode"] = "del"
        await q.message.reply_text("Номер комментария:\n\n" + text, reply_markup=cancel_keyboard())

    elif q.data == "cancel":
        context.user_data.clear()
        await q.message.reply_text("Отменено", reply_markup=comments_keyboard())

    elif q.data == "back":
        context.user_data.clear()
        await q.message.reply_text("Главное меню:", reply_markup=main_keyboard())

# ================= MESSAGES =================

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    mode = context.user_data.get("mode")
    comments = load_comments()

    if not mode:
        await update.message.reply_text("Выберите действие:", reply_markup=main_keyboard())
        return

    if mode == "add":
        comments.append(text)
        save_comments(comments)
        await update.message.reply_text("Добавлено ✅", reply_markup=comments_keyboard())

    elif mode == "edit":
        if " " not in text:
            await update.message.reply_text("Пример:\n2 Новый текст")
            return

        num, new = text.split(" ", 1)

        if not num.isdigit():
            await update.message.reply_text("Номер должен быть числом")
            return

        i = int(num) - 1

        if i < 0 or i >= len(comments):
            await update.message.reply_text("Такого номера нет")
            return

        comments[i] = new
        save_comments(comments)
        await update.message.reply_text("Изменено ✅", reply_markup=comments_keyboard())

    elif mode == "del":
        if not text.isdigit():
            await update.message.reply_text("Напишите номер")
            return

        i = int(text) - 1

        if i < 0 or i >= len(comments):
            await update.message.reply_text("Такого номера нет")
            return

        del comments[i]
        save_comments(comments)
        await update.message.reply_text("Удалено ✅", reply_markup=comments_keyboard())

    context.user_data.clear()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Панель управления:", reply_markup=main_keyboard())

# ================= MAIN =================

async def post_init(app):
    app.create_task(vk_worker(app))

async def error_handler(update, context):
    logging.error("Ошибка:", exc_info=context.error)

def main():
    global bot_running
    bot_running = True  # Установим bot_running как True с самого начала
    app = Application.builder().token(TG_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT, messages))

    app.run_polling()

    app.add_error_handler(error_handler)

if __name__ == "__main__":
    main()