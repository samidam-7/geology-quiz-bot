#!/usr/bin/env python3
"""
بوت الاختبارات - Quiz Bot
Python 3.13 + python-telegram-bot + Neon.tech PostgreSQL

المواضيع المتاحة:
  - جيولوجيا        (836 سؤال)
  - hay2_general    (296 سؤال) ─┐
  - hay2_important  (155 سؤال)  ├─ حيوان 2
  - hay2_drawings   (105 سؤال) ─┘
  - en_*            (أسئلة اللغة الإنجليزية)
"""

import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import (
    init_db,
    register_user,
    get_questions_by_subject,
    get_user_mistakes,
    create_session,
    record_answer,
    close_session,
    get_user_stats,
    get_leaderboard,
    save_pending_subject,
    get_pending_subject,
    get_subject_counts,
)

load_dotenv()

# ─────────────────────────────────────────
# إعداد التسجيل
# ─────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# متغيرات البيئة
# ─────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
]

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")

# ─────────────────────────────────────────
# تعريف المواضيع وعرضها للمستخدم
# ─────────────────────────────────────────
# المفاتيح في القاعدة → النص في القائمة
SUBJECTS: dict[str, str] = {
    "جيولوجيا":      "🪨 جيولوجيا",
    "hay2_general":  "🦁 حيوان 2 — عام",
    "hay2_important":"⭐ حيوان 2 — مهم",
    "hay2_drawings": "🖼 حيوان 2 — رسوميات",
}

# مجموعات القائمة الرئيسية
MAIN_CATEGORIES = {
    "geo":     ("🪨 جيولوجيا",    ["جيولوجيا"]),
    "hay2":    ("🦁 حيوان 2",     ["hay2_general", "hay2_important", "hay2_drawings"]),
    "english": ("🇬🇧 إنجليزي",    None),   # سيُعرض قائمة فرعية
}

ENGLISH_SUBJECTS: dict[str, str] = {
    "en_pres_simple":    "فعل المضارع البسيط",
    "en_pres_cont":      "المضارع المستمر",
    "en_pres_perfect":   "المضارع التام",
    "en_pres_perf_cont": "المضارع التام المستمر",
    "en_past_simple":    "الماضي البسيط",
    "en_past_cont":      "الماضي المستمر",
    "en_past_perfect":   "الماضي التام",
    "en_future":         "المستقبل",
    "en_conditionals":   "الجمل الشرطية",
    "en_comparative":    "أسماء التفضيل",
    "en_reflexive":      "الضمائر الانعكاسية",
    "en_used_to":        "used to",
    "en_obligation":     "الالتزام (must/have to)",
    "en_deduction":      "الاستنتاج (must/can't)",
    "en_strong_adj":     "الصفات القوية",
    "en_course_q":       "أسئلة الكورس",
}

# ─────────────────────────────────────────
# حالة المستخدمين
# ─────────────────────────────────────────
user_states: dict[int, dict] = {}


# ─────────────────────────────────────────
# لوحة مفاتيح القائمة الرئيسية
# ─────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪨 جيولوجيا",      callback_data="cat_geo")],
        [InlineKeyboardButton("🦁 حيوان 2",        callback_data="cat_hay2")],      # ← الزر المُصلح
        [InlineKeyboardButton("🇬🇧 إنجليزي",      callback_data="cat_english")],
        [InlineKeyboardButton("🔁 مراجعة أخطائي", callback_data="cat_review")],
        [InlineKeyboardButton("🏆 المتصدرون",      callback_data="leaderboard")],
        [InlineKeyboardButton("📊 إحصائياتي",     callback_data="my_stats")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main")]
    ])


# ─────────────────────────────────────────
# لوحة مفاتيح حيوان 2 (مُصلح)
# ─────────────────────────────────────────
def hay2_keyboard(counts: dict) -> InlineKeyboardMarkup:
    """
    يعرض الأقسام الثلاثة لحيوان 2 مع عدد الأسئلة.
    هذا هو الإصلاح الرئيسي لمشكلة 'زر حيوان 2 لا يظهر محتوياته'.
    """
    rows = []
    for subj, label in [
        ("hay2_general",   "🦁 عام"),
        ("hay2_important", "⭐ مهم"),
        ("hay2_drawings",  "🖼 رسوميات"),
    ]:
        n = counts.get(subj, 0)
        rows.append([
            InlineKeyboardButton(
                f"{label}  ({n} سؤال)",
                callback_data=f"subj_{subj}",
            )
        ])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────
# لوحة مفاتيح الإنجليزي
# ─────────────────────────────────────────
def english_keyboard(counts: dict) -> InlineKeyboardMarkup:
    rows = []
    for subj, label in ENGLISH_SUBJECTS.items():
        n = counts.get(subj, 0)
        rows.append([
            InlineKeyboardButton(
                f"{label} ({n})",
                callback_data=f"subj_{subj}",
            )
        ])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────
# لوحة مفاتيح عدد الأسئلة
# ─────────────────────────────────────────
def count_keyboard(subject: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("20 سؤال",  callback_data=f"cnt_{subject}_20"),
            InlineKeyboardButton("40 سؤال",  callback_data=f"cnt_{subject}_40"),
            InlineKeyboardButton("كل الأسئلة", callback_data=f"cnt_{subject}_0"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


# ═══════════════════════════════════════════
# معالجات الأوامر
# ═══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # تسجيل المستخدم في القاعدة
    await register_user(
        user.id,
        user.username or "",
        user.first_name or "",
        user.last_name or "",
    )
    text = (
        f"👋 أهلاً {user.first_name}!\n\n"
        "📚 بوت الاختبارات التعليمي\n"
        "اختر موضوعاً لتبدأ الاختبار:\n"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 القائمة الرئيسية:",
        reply_markup=main_menu_keyboard(),
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    state = user_states.pop(chat_id, None)
    if state and state.get("session_id", -1) >= 0:
        await close_session(state["session_id"])
    if state:
        await update.message.reply_text(
            "⏹ تم إيقاف الاختبار.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text("لا يوجد اختبار نشط.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        # إظهار إحصائيات المستخدم لنفسه
        data = await get_user_stats(user.id)
        if not data or not data.get("sessions"):
            await update.message.reply_text("لم تُكمل أي اختبار بعد.")
            return
        total_q = data.get("total_q") or 0
        correct = data.get("total_correct") or 0
        wrong   = data.get("total_wrong") or 0
        pct = round(correct / total_q * 100, 1) if total_q else 0
        await update.message.reply_text(
            f"📊 إحصائياتك:\n"
            f"جلسات مكتملة: {data['sessions']}\n"
            f"إجمالي الأسئلة: {total_q}\n"
            f"✅ صحيح: {correct} ({pct}%)\n"
            f"❌ خطأ: {wrong}\n"
            f"📝 أخطاء متراكمة: {data.get('mistakes', 0)}"
        )
        return

    # إحصائيات المسؤول
    active = len(user_states)
    await update.message.reply_text(
        f"📊 إحصائيات المسؤول:\n"
        f"👥 مستخدمون نشطون: {active}\n"
        f"🔑 معرفك: {user.id}"
    )


# ═══════════════════════════════════════════
# معالجات الأزرار (CallbackQuery)
# ═══════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    user    = query.from_user

    # ── القائمة الرئيسية ──────────────────────
    if data == "back_main":
        await query.edit_message_text(
            "📚 القائمة الرئيسية:",
            reply_markup=main_menu_keyboard(),
        )
        return

    # ── جيولوجيا مباشرة ──────────────────────
    if data == "cat_geo":
        await query.edit_message_text(
            "🪨 جيولوجيا — كم عدد الأسئلة؟",
            reply_markup=count_keyboard("جيولوجيا"),
        )
        return

    # ── حيوان 2 — يعرض القائمة الفرعية ────────
    #    هذا هو إصلاح المشكلة الرئيسية:
    #    كان الزر غائباً لأنه لم يكن يوجد handler له
    if data == "cat_hay2":
        counts = await get_subject_counts()
        await query.edit_message_text(
            "🦁 حيوان 2 — اختر القسم:",
            reply_markup=hay2_keyboard(counts),
        )
        return

    # ── الإنجليزي — قائمة فرعية ──────────────
    if data == "cat_english":
        counts = await get_subject_counts()
        await query.edit_message_text(
            "🇬🇧 اللغة الإنجليزية — اختر الموضوع:",
            reply_markup=english_keyboard(counts),
        )
        return

    # ── مراجعة الأخطاء ───────────────────────
    if data == "cat_review":
        mistakes = await get_user_mistakes(user.id)
        if not mistakes:
            await query.edit_message_text(
                "🎉 لا توجد أخطاء متراكمة لديك!",
                reply_markup=back_keyboard(),
            )
            return
        await _start_quiz(query, context, chat_id, user, mistakes,
                         subject="review", is_review=True)
        return

    # ── قائمة المتصدرين ───────────────────────
    if data == "leaderboard":
        rows = await get_leaderboard(10)
        if not rows:
            text = "🏆 القائمة فارغة بعد."
        else:
            lines = ["🏆 أفضل 10 نتائج:\n"]
            for i, r in enumerate(rows, 1):
                name = r.get("first_name") or f"#{r['user_id']}"
                lines.append(f"{i}. {name} — {r['total_correct']}/{r['total_q']}")
            text = "\n".join(lines)
        await query.edit_message_text(text, reply_markup=back_keyboard())
        return

    # ── إحصائياتي ────────────────────────────
    if data == "my_stats":
        stats = await get_user_stats(user.id)
        if not stats or not stats.get("sessions"):
            await query.edit_message_text(
                "لم تُكمل أي اختبار بعد.",
                reply_markup=back_keyboard(),
            )
            return
        total_q = stats.get("total_q") or 0
        correct = stats.get("total_correct") or 0
        wrong   = stats.get("total_wrong") or 0
        pct = round(correct / total_q * 100, 1) if total_q else 0
        text = (
            f"📊 إحصائياتك:\n"
            f"جلسات مكتملة: {stats['sessions']}\n"
            f"إجمالي الأسئلة: {total_q}\n"
            f"✅ صحيح: {correct} ({pct}%)\n"
            f"❌ خطأ: {wrong}\n"
            f"📝 أخطاء متراكمة: {stats.get('mistakes', 0)}"
        )
        await query.edit_message_text(text, reply_markup=back_keyboard())
        return

    # ── اختيار موضوع فرعي (subj_...) ──────────
    if data.startswith("subj_"):
        subject = data[5:]   # إزالة "subj_"
        await query.edit_message_text(
            f"📚 {SUBJECTS.get(subject, subject)}\nكم عدد الأسئلة؟",
            reply_markup=count_keyboard(subject),
        )
        return

    # ── اختيار عدد الأسئلة (cnt_subject_N) ────
    if data.startswith("cnt_"):
        # cnt_<subject>_<limit>  — الموضوع قد يحتوي على "_"
        parts = data[4:].rsplit("_", 1)
        if len(parts) != 2:
            await query.answer("بيانات غير صحيحة.", show_alert=True)
            return
        subject, limit_str = parts
        limit = int(limit_str) if limit_str.isdigit() else 0

        questions = await get_questions_by_subject(subject, limit)
        if not questions:
            await query.edit_message_text(
                f"⚠️ لا توجد أسئلة في هذا الموضوع.",
                reply_markup=back_keyboard(),
            )
            return
        await _start_quiz(query, context, chat_id, user, questions,
                         subject=subject, is_review=False)
        return


# ─────────────────────────────────────────
# بدء الاختبار (مشترك)
# ─────────────────────────────────────────
async def _start_quiz(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    questions: list,
    subject: str,
    is_review: bool,
) -> None:
    total = len(questions)
    session_id = await create_session(user.id, subject, total, is_review)

    user_states[chat_id] = {
        "questions":  questions,
        "current":    0,
        "score":      0,
        "total":      total,
        "subject":    subject,
        "session_id": session_id,
        "user_id":    user.id,
        "is_review":  is_review,
    }

    label = "مراجعة الأخطاء" if is_review else SUBJECTS.get(subject, subject)
    await query.edit_message_text(
        f"🎯 {label}\n"
        f"عدد الأسئلة: {total}\n\n"
        f"أجب بـ: أ / ب / ج / د  أو  a / b / c / d\n"
        f"للإيقاف: /stop"
    )
    await send_question(chat_id, context)


# ─────────────────────────────────────────
# إرسال سؤال
# ─────────────────────────────────────────
async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.get(chat_id)
    if not state:
        return

    idx   = state["current"]
    total = state["total"]

    if idx >= total:
        await finish_quiz(chat_id, context)
        return

    q = state["questions"][idx]

    # بناء نص السؤال
    question_text = q.get("question") or q.get("question_text", "")
    option_a = q.get("option_a", "")
    option_b = q.get("option_b", "")
    option_c = q.get("option_c", "")
    option_d = q.get("option_d", "")

    # إذا كانت الخيارات موجودة بشكل منفصل، أضفها
    if option_a and "أ)" not in question_text and "الف)" not in question_text:
        body = (
            f"{question_text}\n\n"
            f"أ) {option_a}\n"
            f"ب) {option_b}\n"
            f"ج) {option_c}\n"
            f"د) {option_d}"
        )
    else:
        body = question_text

    text = f"📝 سؤال {idx + 1}/{total}:\n\n{body}"
    await context.bot.send_message(chat_id=chat_id, text=text)


# ─────────────────────────────────────────
# إنهاء الاختبار
# ─────────────────────────────────────────
async def finish_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.pop(chat_id, None)
    if not state:
        return

    score   = state["score"]
    total   = state["total"]
    pct     = round(score / total * 100) if total else 0
    sid     = state.get("session_id", -1)

    await close_session(sid)

    if pct == 100:   medal = "🏆 ممتاز! تسلط كامل."
    elif pct >= 80:  medal = "👏 عالي جداً!"
    elif pct >= 60:  medal = "👍 جيد!"
    elif pct >= 40:  medal = "📚 يحتاج مراجعة."
    else:            medal = "💪 استمر في التعلم!"

    text = (
        f"🏁 انتهى الاختبار!\n\n"
        f"📊 النتيجة: {score}/{total}\n"
        f"📈 النسبة: {pct}%\n\n"
        f"{medal}"
    )
    await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=main_menu_keyboard()
    )


# ─────────────────────────────────────────
# معالج الرسائل النصية (إجابات)
# ─────────────────────────────────────────
ANSWER_MAP = {
    "a": "a", "b": "b", "c": "c", "d": "d",
    "أ": "a", "ب": "b", "ج": "c", "د": "d",
    "الف": "a", "ب": "b",
}


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text    = update.message.text.strip()
    state   = user_states.get(chat_id)

    if not state:
        await update.message.reply_text(
            "لم تبدأ اختباراً. اضغط /start",
            reply_markup=main_menu_keyboard(),
        )
        return

    idx = state["current"]
    q   = state["questions"][idx]

    correct_answer = (q.get("answer") or q.get("correct_answer", "")).lower().strip()
    user_answer    = ANSWER_MAP.get(text.lower(), text.lower()[:1])

    is_correct = user_answer == correct_answer

    # تسجيل الإجابة في القاعدة
    await record_answer(
        session_id=state["session_id"],
        user_id=state["user_id"],
        question_id=q.get("id", 0),
        user_answer=user_answer,
        is_correct=is_correct,
    )

    if is_correct:
        state["score"] += 1
        explanation = q.get("explanation", "")
        feedback = f"✅ صحيح!{chr(10) + chr(10) + '💡 ' + explanation if explanation else ''}"
    else:
        # الخيار الصحيح بالنص
        correct_letter = correct_answer.upper()
        opt_map = {"A": q.get("option_a",""), "B": q.get("option_b",""),
                   "C": q.get("option_c",""), "D": q.get("option_d","")}
        correct_text = opt_map.get(correct_letter, correct_letter)
        explanation = q.get("explanation", "")
        feedback = (
            f"❌ خطأ.\n"
            f"الجواب الصحيح: {correct_letter}) {correct_text}\n"
            f"{chr(10) + '💡 ' + explanation if explanation else ''}"
        )

    state["current"] += 1
    await update.message.reply_text(feedback)
    await asyncio.sleep(1.5)
    await send_question(chat_id, context)


# ═══════════════════════════════════════════
# نقطة الدخول
# ═══════════════════════════════════════════
def main() -> None:
    # تهيئة القاعدة
    logger.info("🔄 تهيئة قاعدة البيانات...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ تعذّر الاتصال بقاعدة البيانات: {e}")

    app = Application.builder().token(BOT_TOKEN).build()

    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu",  menu_cmd))
    app.add_handler(CommandHandler("stop",  stop_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    # ─────────────────────────────────────────────────────
    # معالجات الأزرار — نمط شامل يغطي كل callback_data
    # ─────────────────────────────────────────────────────
    # • cat_geo | cat_hay2 | cat_english | cat_review  → القائمة الرئيسية
    # • subj_<subject>                                 → اختيار موضوع
    # • cnt_<subject>_<limit>                          → اختيار عدد الأسئلة
    # • leaderboard | my_stats | back_main             → وظائف أخرى
    app.add_handler(CallbackQueryHandler(button_handler))

    # الرسائل النصية (الإجابات)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    logger.info("🚀 البوت يعمل الآن...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
