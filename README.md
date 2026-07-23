# 🤖 بوت الاختبارات — Quiz Bot

بوت تلغرام تعليمي يقدم اختبارات في الجيولوجيا، علم الحيوان، واللغة الإنجليزية.

## المواضيع المتاحة

| الموضوع | المفتاح في القاعدة | عدد الأسئلة |
|---------|-------------------|-------------|
| 🪨 جيولوجيا | `جيولوجيا` | 836 |
| 🦁 حيوان 2 — عام | `hay2_general` | 296 |
| ⭐ حيوان 2 — مهم | `hay2_important` | 155 |
| 🖼 حيوان 2 — رسوميات | `hay2_drawings` | 105 |
| 🇬🇧 إنجليزي | `en_*` | 16 موضوع |

## المتطلبات

- Python 3.13+
- قاعدة بيانات PostgreSQL (Neon.tech)

## الإعداد (Replit Secrets)

| المتغير | الوصف |
|---------|-------|
| `BOT_TOKEN` | توكن بوت تلغرام من @BotFather |
| `DATABASE_URL` | رابط Neon.tech PostgreSQL |
| `ADMIN_IDS` | معرفات المسؤولين (env var، مفصولة بفاصلة) |

## تشغيل البوت

```bash
pip install -r requirements.txt
python bot.py
```

## الأوامر

| الأمر | الوصف |
|-------|-------|
| `/start` | القائمة الرئيسية |
| `/menu` | القائمة الرئيسية |
| `/stop` | إيقاف الاختبار الحالي |
| `/stats` | إحصائيات المستخدم / المسؤول |

## بنية الملفات

```
├── bot.py          # البوت الرئيسي — handlers وأوامر
├── database.py     # طبقة قاعدة البيانات
├── requirements.txt
├── .env.example    # مثال متغيرات البيئة
└── README.md
```

## مخطط قاعدة البيانات

```
questions          — الأسئلة (subject, question_text, option_a..d, correct_answer)
users              — المستخدمون
quiz_sessions      — جلسات الاختبار (correct/wrong/total)
quiz_answers       — إجابات كل سؤال
user_mistakes      — الأخطاء المتراكمة لكل مستخدم
user_pending_subject — آخر موضوع مختار
```

## إصلاح مشكلة "زر حيوان 2 لا يظهر"

**السبب:** كان الكود القديم لا يحتوي على handler لـ `cat_hay2`، ولم تكن فئة `animal_2` موجودة في القاعدة.

**الحل:**
1. ربط الزر بالمواضيع الحقيقية (`hay2_general`, `hay2_important`, `hay2_drawings`)
2. إضافة `cat_hay2` handler يعرض قائمة فرعية بالأقسام الثلاثة مع عدد الأسئلة
3. استخدام `CallbackQueryHandler(button_handler)` شامل بدلاً من patterns محدودة

```python
# الزر يعرض قائمة فرعية بالأقسام الثلاثة
if data == "cat_hay2":
    counts = await get_subject_counts()
    await query.edit_message_text(
        "🦁 حيوان 2 — اختر القسم:",
        reply_markup=hay2_keyboard(counts),
    )
```
