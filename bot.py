#!/usr/bin/env python3
"""
بوت اختبارات تلغرام - Geology & Animal Quiz Bot
يدعم: أسئلة زمين‌شناسی + حيوان 1 + حيوان 2
قاعدة بيانات: Neon.tech PostgreSQL
"""

import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import init_db, get_questions_by_category, save_score, get_leaderboard

load_dotenv()

# ==========================================
# إعداد التسجيل
# ==========================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==========================================
# المتغيرات الأساسية
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")

# ==========================================
# حالة المستخدمين في الذاكرة
# ==========================================
user_states: dict = {}

# ==========================================
# فئات الاختبار
# ==========================================
CATEGORIES = {
    "geology": {
        "label": "🪨 سنگ‌شناسی (زمین‌شناسی)",
        "callback": "cat_geology",
    },
    "animal_1": {
        "label": "🐾 حيوان 1",
        "callback": "cat_animal_1",
    },
    "animal_2": {
        "label": "🦁 حيوان 2",
        "callback": "cat_animal_2",
    },
}

# ==========================================
# أزرار القائمة الرئيسية
# ==========================================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(CATEGORIES["geology"]["label"],  callback_data="cat_geology")],
        [InlineKeyboardButton(CATEGORIES["animal_1"]["label"], callback_data="cat_animal_1")],
        [InlineKeyboardButton(CATEGORIES["animal_2"]["label"], callback_data="cat_animal_2")],
        [InlineKeyboardButton("🏆 قائمة المتصدرين", callback_data="leaderboard")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==========================================
# أمر /start
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_text = (
        f"👋 مرحباً {user.first_name}!\n\n"
        "🎓 بوت الاختبارات التعليمي\n"
        "اختر فئة للبدء:\n\n"
        "🪨 سنگ‌شناسی — ۶۰ سوال زمین‌شناسی\n"
        "🐾 حيوان 1 — أسئلة عن الحيوانات (الجزء الأول)\n"
        "🦁 حيوان 2 — أسئلة عن الحيوانات (الجزء الثاني)\n"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
    )


# ==========================================
# أمر /menu
# ==========================================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 القائمة الرئيسية — اختر فئة:",
        reply_markup=main_menu_keyboard(),
    )


# ==========================================
# معالج أزرار الفئات
# ==========================================
async def category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data  # مثل: "cat_geology" أو "cat_animal_1" أو "cat_animal_2"

    # تحديد الفئة من callback_data
    category_map = {
        "cat_geology":  "geology",
        "cat_animal_1": "animal_1",
        "cat_animal_2": "animal_2",
    }

    category_key = category_map.get(data)
    if not category_key:
        await query.edit_message_text("❌ فئة غير معروفة. يرجى الضغط /start")
        return

    # جلب الأسئلة من قاعدة البيانات
    questions = await get_questions_by_category(category_key)

    if not questions:
        await query.edit_message_text(
            f"⚠️ لا توجد أسئلة في هذه الفئة بعد.\n"
            f"الفئة: {CATEGORIES[category_key]['label']}\n\n"
            f"يمكن للمسؤول إضافة أسئلة.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
            ),
        )
        return

    # تهيئة حالة المستخدم
    user_states[chat_id] = {
        "category": category_key,
        "questions": questions,
        "current": 0,
        "score": 0,
        "total": len(questions),
    }

    cat_label = CATEGORIES[category_key]["label"]
    await query.edit_message_text(
        f"🎯 {cat_label}\n"
        f"عدد الأسئلة: {len(questions)}\n\n"
        f"اكتب جوابك بالحرف (أ / ب / ج / د) أو (a / b / c / d).\n"
        f"للإلغاء اكتب /stop"
    )

    # إرسال السؤال الأول
    await send_question(chat_id, context)


# ==========================================
# إرسال سؤال
# ==========================================
async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.get(chat_id)
    if not state:
        return

    idx = state["current"]
    total = state["total"]

    if idx >= total:
        await finish_quiz(chat_id, context)
        return

    q = state["questions"][idx]
    question_text = (
        f"📝 سوال {idx + 1} از {total}:\n\n"
        f"{q['question']}"
    )
    await context.bot.send_message(chat_id=chat_id, text=question_text)


# ==========================================
# انتهاء الاختبار
# ==========================================
async def finish_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.pop(chat_id, None)
    if not state:
        return

    score = state["score"]
    total = state["total"]
    percent = round((score / total) * 100) if total > 0 else 0

    if percent == 100:
        result_emoji = "🏆 ممتاز! تسلط كامل."
    elif percent >= 80:
        result_emoji = "👏 عالي جداً!"
    elif percent >= 60:
        result_emoji = "👍 جيد!"
    elif percent >= 40:
        result_emoji = "📚 يحتاج لمراجعة."
    else:
        result_emoji = "💪 استمر في التعلم!"

    summary = (
        f"🏁 انتهى الاختبار!\n\n"
        f"📊 النتيجة: {score} من {total}\n"
        f"📈 النسبة: {percent}%\n\n"
        f"{result_emoji}"
    )

    # حفظ النتيجة في قاعدة البيانات
    try:
        await save_score(chat_id, state["category"], score, total)
    except Exception as e:
        logger.error(f"خطأ في حفظ النتيجة: {e}")

    await context.bot.send_message(
        chat_id=chat_id,
        text=summary,
        reply_markup=main_menu_keyboard(),
    )


# ==========================================
# معالج الرسائل النصية (إجابات المستخدم)
# ==========================================
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    state = user_states.get(chat_id)
    if not state:
        # المستخدم لم يبدأ اختباراً
        await update.message.reply_text(
            "لم تبدأ اختباراً بعد. اضغط /start للبدء.",
            reply_markup=main_menu_keyboard(),
        )
        return

    idx = state["current"]
    q = state["questions"][idx]
    correct_answer = q["answer"].strip()

    # قبول الإجابة باللغتين العربية والإنجليزية
    answer_map = {
        "a": "أ", "b": "ب", "c": "ج", "d": "د",
        "alef": "أ", "beh": "ب", "jeem": "ج", "dal": "د",
        # فارسی
        "الف": "أ",
    }
    user_answer = answer_map.get(text.lower(), text)

    is_correct = (
        user_answer == correct_answer
        or text.lower() == correct_answer.lower()
        or text == correct_answer
    )

    if is_correct:
        state["score"] += 1
        feedback = f"✅ صحيح!\n\n💡 {q.get('explanation', '')}"
    else:
        feedback = (
            f"❌ خطأ.\n"
            f"الجواب الصحيح: {correct_answer}\n\n"
            f"💡 {q.get('explanation', '')}"
        )

    state["current"] += 1
    await update.message.reply_text(feedback)

    # انتظر قليلاً ثم أرسل السؤال التالي
    await asyncio.sleep(1.5)
    await send_question(chat_id, context)


# ==========================================
# أمر /stop
# ==========================================
async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in user_states:
        del user_states[chat_id]
        await update.message.reply_text(
            "⏹ تم إيقاف الاختبار.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text("لا يوجد اختبار نشط.")


# ==========================================
# قائمة المتصدرين
# ==========================================
async def leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        rows = await get_leaderboard(limit=10)
        if not rows:
            text = "🏆 قائمة المتصدرين فارغة بعد."
        else:
            lines = ["🏆 أفضل 10 نتائج:\n"]
            for i, row in enumerate(rows, 1):
                lines.append(
                    f"{i}. المستخدم #{row['user_id']} — "
                    f"{row['score']}/{row['total']} ({row['category']})"
                )
            text = "\n".join(lines)
    except Exception as e:
        logger.error(f"خطأ في جلب المتصدرين: {e}")
        text = "⚠️ خطأ في جلب قائمة المتصدرين."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
        ),
    )


# ==========================================
# معالج الرجوع للقائمة الرئيسية
# ==========================================
async def back_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📚 القائمة الرئيسية — اختر فئة:",
        reply_markup=main_menu_keyboard(),
    )


# ==========================================
# أوامر المسؤول
# ==========================================
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ ليس لديك صلاحية.")
        return

    active_users = len(user_states)
    await update.message.reply_text(
        f"📊 إحصائيات المسؤول:\n"
        f"👥 المستخدمون النشطون: {active_users}\n"
        f"🔑 معرفك: {user_id}"
    )


# ==========================================
# نقطة الدخول الرئيسية
# ==========================================
def main() -> None:
    # تهيئة قاعدة البيانات
    logger.info("🔄 تهيئة قاعدة البيانات...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ تعذّر الاتصال بقاعدة البيانات: {e}")
        logger.warning("سيعمل البوت بالأسئلة الاحتياطية المدمجة.")

    # إنشاء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("menu",   menu))
    app.add_handler(CommandHandler("stop",   stop_quiz))
    app.add_handler(CommandHandler("stats",  admin_stats))

    # ===================================================
    # معالجات الأزرار — مرتبة من الأكثر تحديداً إلى الأقل
    # ===================================================
    # أزرار الفئات (cat_geology, cat_animal_1, cat_animal_2)
    app.add_handler(
        CallbackQueryHandler(category_handler, pattern=r"^cat_(geology|animal_1|animal_2)$")
    )
    # قائمة المتصدرين
    app.add_handler(
        CallbackQueryHandler(leaderboard_handler, pattern=r"^leaderboard$")
    )
    # الرجوع للقائمة
    app.add_handler(
        CallbackQueryHandler(back_main_handler, pattern=r"^back_main$")
    )

    # رسائل النص (الإجابات)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)
    )

    logger.info("🚀 البوت يعمل...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
