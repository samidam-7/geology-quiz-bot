# بوت الاختبارات - Geology & Animals Quiz Bot

بوت تلغرام تعليمي يقدم اختبارات في مجالات الزمين‌شناسی والحيوانات، مع قاعدة بيانات Neon.tech.

## تشغيل البوت

```bash
python bot.py
```

## المتغيرات المطلوبة (Secrets)

| المتغير | الوصف |
|---------|-------|
| `BOT_TOKEN` | توكن بوت تلغرام من @BotFather |
| `DATABASE_URL` | رابط قاعدة بيانات Neon.tech PostgreSQL |
| `ADMIN_IDS` | معرفات المسؤولين (env var) |

## Stack

- Python 3.13
- python-telegram-bot 22.8
- psycopg2-binary (Neon.tech PostgreSQL)
- python-dotenv

## Where things live

- `bot.py` — الملف الرئيسي: handlers, commands, bot setup
- `database.py` — قاعدة البيانات: init, CRUD, seed
- `requirements.txt` — مكتبات Python
- `README.md` — توثيق كامل

## GitHub

- المستودع: https://github.com/reza200413831354-crypto/geology-quiz-bot
- Remote: origin → https://github.com/reza200413831354-crypto/geology-quiz-bot.git

## User preferences

- لا تشغّل البوت (no auto-run/workflow)
- استخدم Neon.tech كقاعدة بيانات خارجية
- Python 3.13 فقط
- ادفع التعديلات تلقائياً لـ GitHub

## Gotchas

- `DATABASE_URL` مُعالَج من Replit لذا استخدم نفس المتغير — psycopg2 يتصل بـ Neon.tech عبره
- `init_db()` يُضيف أسئلة ابتدائية تلقائياً إذا كانت الجداول فارغة
- زر "حيوان 2" كان معطلاً بسبب غياب callback handler — تم إصلاحه بـ regex pattern
