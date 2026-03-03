# ====== VK ======
VK_TOKEN = "ВСТАВЬ_СЮДА_VK_ТОКЕН"
GROUP_ID = int(os.getenv("GROUP_ID", "-123456789"))

# ====== TELEGRAM ======
TG_TOKEN = "ВСТАВЬ_СЮДА_TELEGRAM_BOT_TOKEN"
USER_ID = int(os.getenv("USER_ID", "123456789"))

# ====== НАСТРОЙКИ ======
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
COMMENTS_FILE = os.getenv("COMMENTS_FILE", "comments.txt")
DB_FILE = os.getenv("DB_FILE", "processed_posts.db")
