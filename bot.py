#!/usr/bin/env python3
"""
بوت الاختبارات — Quiz Bot
Python 3.13 + python-telegram-bot + Neon.tech PostgreSQL

المواضيع:
  - جيولوجيا        (836 سؤال)
  - hay2_general    (296 سؤال)
  - hay2_important  (155 سؤال)
  - hay2_drawings   (105 سؤال / 12 رسمة)
  - en_*            (أسئلة اللغة الإنجليزية)
"""

import os
import re
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
# عناوين المواضيع
# ─────────────────────────────────────────
SUBJECTS: dict[str, str] = {
    "جيولوجيا":       "🪨 جيولوجيا",
    "hay2_general":   "🦁 حيوان 2 — عام",
    "hay2_important": "⭐ حيوان 2 — مهم",
    "hay2_drawings":  "🖼 أسئلة الرسمات",
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


# ═══════════════════════════════════════════════════════════
# نظام تحليل أسئلة الرسمات
# ═══════════════════════════════════════════════════════════

# تنسيق السؤال: "📌 الرسمة N: عنوان الرسمة — نص السؤال"
_DRAWING_RE = re.compile(
    r"📌\s*الرسمة\s*(\d+)\s*[:\s]+([^—–\-]+?)\s*[—–\-]+\s*(.*)",
    re.DOTALL,
)


def parse_drawing_info(question_text: str) -> tuple[int, str, str]:
    """
    يحلل نص السؤال ويستخرج:
      - رقم الرسمة
      - عنوان الرسمة
      - نص السؤال فقط (بدون البادئة)
    """
    m = _DRAWING_RE.match(question_text.strip())
    if m:
        num   = int(m.group(1))
        title = m.group(2).strip()
        q_txt = m.group(3).strip()
        return num, title, q_txt
    return 0, "", question_text.strip()


def group_questions_by_drawing(questions: list) -> list[dict]:
    """
    يجمّع الأسئلة في مجموعات حسب رقم الرسمة.
    المُخرج: قائمة من dict:
        { "num": int, "title": str, "questions": [q, ...] }
    مع إضافة "q_text" لكل سؤال (النص النظيف بدون بادئة الرسمة).
    """
    groups: dict[int, dict] = {}
    order: list[int] = []

    for q in questions:
        raw = q.get("question") or q.get("question_text", "")
        num, title, clean_text = parse_drawing_info(raw)

        if num not in groups:
            groups[num] = {"num": num, "title": title, "questions": []}
            order.append(num)

        # نسخة معدّلة من السؤال بنص نظيف
        q_copy = dict(q)
        q_copy["q_text"] = clean_text
        groups[num]["questions"].append(q_copy)

    return [groups[n] for n in order]


# ─────────────────────────────────────────
# لوحات المفاتيح
# ─────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪨 جيولوجيا",       callback_data="cat_geo")],
        [InlineKeyboardButton("🦁 حيوان 2",         callback_data="cat_hay2")],
        [InlineKeyboardButton("🇬🇧 إنجليزي",       callback_data="cat_english")],
        [InlineKeyboardButton("🔁 مراجعة أخطائي",  callback_data="cat_review")],
        [InlineKeyboardButton("🏆 المتصدرون",       callback_data="leaderboard")],
        [InlineKeyboardButton("📊 إحصائياتي",      callback_data="my_stats")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main")]
    ])


def hay2_keyboard(counts: dict) -> InlineKeyboardMarkup:
    rows = []
    for subj, label in [
        ("hay2_general",   "🦁 عام"),
        ("hay2_important", "⭐ مهم"),
        ("hay2_drawings",  "🖼 أسئلة الرسمات"),
    ]:
        n = counts.get(subj, 0)
        rows.append([InlineKeyboardButton(
            f"{label}  ({n} سؤال)",
            callback_data=f"subj_{subj}",
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def english_keyboard(counts: dict) -> InlineKeyboardMarkup:
    rows = []
    for subj, label in ENGLISH_SUBJECTS.items():
        n = counts.get(subj, 0)
        rows.append([InlineKeyboardButton(
            f"{label} ({n})", callback_data=f"subj_{subj}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def count_keyboard(subject: str) -> InlineKeyboardMarkup:
    # الرسمات لا تحتاج خيار عدد — تُشغَّل كلها دائماً
    if subject == "hay2_drawings":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 ابدأ جميع الرسمات (12 رسمة)", callback_data=f"cnt_{subject}_0")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("20 سؤال",    callback_data=f"cnt_{subject}_20"),
            InlineKeyboardButton("40 سؤال",    callback_data=f"cnt_{subject}_40"),
            InlineKeyboardButton("كل الأسئلة", callback_data=f"cnt_{subject}_0"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


# ═══════════════════════════════════════════════════════════
# معالجات الأوامر
# ═══════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await register_user(
        user.id, user.username or "",
        user.first_name or "", user.last_name or "",
    )
    await update.message.reply_text(
        f"👋 أهلاً {user.first_name}!\n\n"
        "📚 بوت الاختبارات التعليمي\n"
        "اختر موضوعاً لتبدأ:",
        reply_markup=main_menu_keyboard(),
    )


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📚 القائمة الرئيسية:", reply_markup=main_menu_keyboard())


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    state = user_states.pop(chat_id, None)
    if state and state.get("session_id", -1) >= 0:
        await close_session(state["session_id"])
    if state:
        await update.message.reply_text("⏹ تم إيقاف الاختبار.", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("لا يوجد اختبار نشط.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
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


# ═══════════════════════════════════════════════════════════
# معالج الأزرار (CallbackQuery)
# ═══════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    await query.answer()
    data    = query.data
    chat_id = query.message.chat_id
    user    = query.from_user

    # تسجيل المستخدم دائماً قبل أي عملية (يمنع foreign key error)
    await register_user(
        user.id, user.username or "",
        user.first_name or "", user.last_name or "",
    )

    # ── رجوع للقائمة ────────────────────────────
    if data == "back_main":
        await query.edit_message_text("📚 القائمة الرئيسية:", reply_markup=main_menu_keyboard())
        return

    # ── جيولوجيا ────────────────────────────────
    if data == "cat_geo":
        await query.edit_message_text(
            "🪨 جيولوجيا — كم عدد الأسئلة؟",
            reply_markup=count_keyboard("جيولوجيا"),
        )
        return

    # ── حيوان 2 (قائمة فرعية) ───────────────────
    if data == "cat_hay2":
        counts = await get_subject_counts()
        await query.edit_message_text(
            "🦁 حيوان 2 — اختر القسم:",
            reply_markup=hay2_keyboard(counts),
        )
        return

    # ── إنجليزي ─────────────────────────────────
    if data == "cat_english":
        counts = await get_subject_counts()
        await query.edit_message_text(
            "🇬🇧 اللغة الإنجليزية — اختر الموضوع:",
            reply_markup=english_keyboard(counts),
        )
        return

    # ── مراجعة الأخطاء ──────────────────────────
    if data == "cat_review":
        mistakes = await get_user_mistakes(user.id)
        if not mistakes:
            await query.edit_message_text(
                "🎉 لا توجد أخطاء متراكمة لديك!",
                reply_markup=back_keyboard(),
            )
            return
        await _start_normal_quiz(query, context, chat_id, user, mistakes,
                                 subject="review", is_review=True)
        return

    # ── المتصدرون ───────────────────────────────
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

    # ── إحصائياتي ───────────────────────────────
    if data == "my_stats":
        stats = await get_user_stats(user.id)
        if not stats or not stats.get("sessions"):
            await query.edit_message_text("لم تُكمل أي اختبار بعد.", reply_markup=back_keyboard())
            return
        total_q = stats.get("total_q") or 0
        correct = stats.get("total_correct") or 0
        wrong   = stats.get("total_wrong") or 0
        pct = round(correct / total_q * 100, 1) if total_q else 0
        await query.edit_message_text(
            f"📊 إحصائياتك:\n"
            f"جلسات مكتملة: {stats['sessions']}\n"
            f"إجمالي الأسئلة: {total_q}\n"
            f"✅ صحيح: {correct} ({pct}%)\n"
            f"❌ خطأ: {wrong}\n"
            f"📝 أخطاء متراكمة: {stats.get('mistakes', 0)}",
            reply_markup=back_keyboard(),
        )
        return

    # ── اختيار موضوع فرعي (subj_...) ───────────
    if data.startswith("subj_"):
        subject = data[5:]
        label   = SUBJECTS.get(subject, subject)
        await query.edit_message_text(
            f"📚 {label}\nكم عدد الأسئلة؟",
            reply_markup=count_keyboard(subject),
        )
        return

    # ── اختيار عدد الأسئلة (cnt_subject_N) ──────
    if data.startswith("cnt_"):
        parts = data[4:].rsplit("_", 1)
        if len(parts) != 2:
            await query.answer("بيانات غير صحيحة.", show_alert=True)
            return
        subject, limit_str = parts
        limit = int(limit_str) if limit_str.isdigit() else 0

        questions = await get_questions_by_subject(subject, limit)
        if not questions:
            await query.edit_message_text(
                "⚠️ لا توجد أسئلة في هذا الموضوع.",
                reply_markup=back_keyboard(),
            )
            return

        # ── الرسمات: نظام خاص ──────────────────
        if subject == "hay2_drawings":
            await _start_drawings_quiz(query, context, chat_id, user, questions)
        else:
            await _start_normal_quiz(query, context, chat_id, user, questions,
                                     subject=subject, is_review=False)
        return


# ═══════════════════════════════════════════════════════════
# بدء اختبار عادي
# ═══════════════════════════════════════════════════════════

async def _start_normal_quiz(query, context, chat_id, user, questions,
                              subject, is_review=False) -> None:
    total      = len(questions)
    session_id = await create_session(user.id, subject, total, is_review)

    user_states[chat_id] = {
        "mode":       "normal",
        "questions":  questions,
        "current":    0,
        "score":      0,
        "total":      total,
        "subject":    subject,
        "session_id": session_id,
        "user_id":    user.id,
    }

    label = "مراجعة الأخطاء" if is_review else SUBJECTS.get(subject, subject)
    await query.edit_message_text(
        f"🎯 {label}\n"
        f"عدد الأسئلة: {total}\n\n"
        f"أجب بـ: أ / ب / ج / د  أو  a / b / c / d\n"
        f"للإيقاف: /stop"
    )
    await _send_normal_question(chat_id, context)


# ═══════════════════════════════════════════════════════════
# بدء اختبار الرسمات
# ═══════════════════════════════════════════════════════════

async def _start_drawings_quiz(query, context, chat_id, user, questions) -> None:
    drawings   = group_questions_by_drawing(questions)
    total      = sum(len(d["questions"]) for d in drawings)
    session_id = await create_session(user.id, "hay2_drawings", total, False)

    user_states[chat_id] = {
        "mode":           "drawings",
        "drawings":       drawings,        # [ {num, title, questions:[...]}, ... ]
        "drawing_idx":    0,               # رقم الرسمة الحالية (index في القائمة)
        "q_in_drawing":   0,               # رقم السؤال داخل الرسمة الحالية
        "score":          0,
        "total":          total,
        "session_id":     session_id,
        "user_id":        user.id,
    }

    await query.edit_message_text(
        f"🖼 أسئلة الرسمات\n"
        f"عدد الرسمات: {len(drawings)}\n"
        f"إجمالي الأسئلة: {total}\n\n"
        f"أجب بـ: أ / ب / ج / د  أو  a / b / c / d\n"
        f"للإيقاف: /stop"
    )

    # إعلان الرسمة الأولى ثم إرسال أول سؤال
    await asyncio.sleep(0.8)
    await _announce_drawing(chat_id, context, drawings[0])
    await asyncio.sleep(0.8)
    await _send_drawing_question(chat_id, context)


# ═══════════════════════════════════════════════════════════
# إعلان بداية رسمة جديدة
# ═══════════════════════════════════════════════════════════

async def _announce_drawing(chat_id: int, context, drawing: dict) -> None:
    """يرسل رسالة تعريفية بالرسمة الجديدة وعدد أسئلتها."""
    n     = drawing["num"]
    title = drawing["title"]
    count = len(drawing["questions"])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖼  الرسمة {n}: {title}\n"
            f"عدد الأسئلة: {count}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )


# ═══════════════════════════════════════════════════════════
# إرسال سؤال — الوضع العادي
# ═══════════════════════════════════════════════════════════

async def _send_normal_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.get(chat_id)
    if not state:
        return

    idx   = state["current"]
    total = state["total"]

    if idx >= total:
        await finish_quiz(chat_id, context)
        return

    q = state["questions"][idx]
    await context.bot.send_message(
        chat_id=chat_id,
        text=_format_question(q, idx + 1, total),
    )


# ═══════════════════════════════════════════════════════════
# إرسال سؤال — وضع الرسمات
# ═══════════════════════════════════════════════════════════

async def _send_drawing_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.get(chat_id)
    if not state:
        return

    d_idx = state["drawing_idx"]
    q_idx = state["q_in_drawing"]
    drawings = state["drawings"]

    # كل الرسمات انتهت
    if d_idx >= len(drawings):
        await finish_quiz(chat_id, context)
        return

    drawing  = drawings[d_idx]
    qs       = drawing["questions"]
    q        = qs[q_idx]
    total_q  = len(qs)

    # نص السؤال النظيف بدون بادئة الرسمة
    clean_text = q.get("q_text") or q.get("question") or q.get("question_text", "")
    opt_a = q.get("option_a", "")
    opt_b = q.get("option_b", "")
    opt_c = q.get("option_c", "")
    opt_d = q.get("option_d", "")

    body = f"{clean_text}\n\nأ) {opt_a}\nب) {opt_b}\nج) {opt_c}\nد) {opt_d}" \
           if opt_a else clean_text

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🖼 الرسمة {drawing['num']} | سؤال {q_idx + 1}/{total_q}\n\n"
            f"📝 {body}"
        ),
    )


# ─────────────────────────────────────────
# تنسيق السؤال (عادي)
# ─────────────────────────────────────────

def _format_question(q: dict, num: int, total: int) -> str:
    raw   = q.get("question") or q.get("question_text", "")
    opt_a = q.get("option_a", "")
    opt_b = q.get("option_b", "")
    opt_c = q.get("option_c", "")
    opt_d = q.get("option_d", "")

    if opt_a and "أ)" not in raw and "الف)" not in raw:
        body = f"{raw}\n\nأ) {opt_a}\nب) {opt_b}\nج) {opt_c}\nد) {opt_d}"
    else:
        body = raw

    return f"📝 سؤال {num}/{total}:\n\n{body}"


# ═══════════════════════════════════════════════════════════
# إنهاء الاختبار
# ═══════════════════════════════════════════════════════════

async def finish_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = user_states.pop(chat_id, None)
    if not state:
        return

    score = state["score"]
    total = state["total"]
    pct   = round(score / total * 100) if total else 0

    await close_session(state.get("session_id", -1))

    if pct == 100:  medal = "🏆 ممتاز! تسلط كامل."
    elif pct >= 80: medal = "👏 عالي جداً!"
    elif pct >= 60: medal = "👍 جيد!"
    elif pct >= 40: medal = "📚 يحتاج مراجعة."
    else:           medal = "💪 استمر في التعلم!"

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏁 انتهى الاختبار!\n\n"
            f"📊 النتيجة: {score}/{total}\n"
            f"📈 النسبة: {pct}%\n\n"
            f"{medal}"
        ),
        reply_markup=main_menu_keyboard(),
    )


# ═══════════════════════════════════════════════════════════
# معالج الرسائل النصية (إجابات المستخدم)
# ═══════════════════════════════════════════════════════════

# خريطة تحويل الإجابة إلى حرف لاتيني (a/b/c/d)
ANSWER_MAP: dict[str, str] = {
    "a": "a", "b": "b", "c": "c", "d": "d",
    "أ": "a", "ب": "b", "ج": "c", "د": "d",
    "الف": "a",
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

    mode = state.get("mode", "normal")

    if mode == "drawings":
        await _handle_drawing_answer(chat_id, context, update, text, state)
    else:
        await _handle_normal_answer(chat_id, context, update, text, state)


# ─────────────────────────────────────────
# معالجة إجابة — وضع عادي
# ─────────────────────────────────────────

async def _handle_normal_answer(chat_id, context, update, text, state) -> None:
    idx = state["current"]
    q   = state["questions"][idx]

    correct = (q.get("answer") or q.get("correct_answer", "")).lower().strip()
    given   = ANSWER_MAP.get(text.lower(), text.lower()[:1])
    is_correct = given == correct

    await record_answer(
        session_id=state["session_id"],
        user_id=state["user_id"],
        question_id=q.get("id", 0),
        user_answer=given,
        is_correct=is_correct,
    )

    if is_correct:
        state["score"] += 1
        expl = q.get("explanation", "")
        fb = f"✅ صحيح!{chr(10) + chr(10) + '💡 ' + expl if expl else ''}"
    else:
        cl = correct.upper()
        opts = {"A": q.get("option_a",""), "B": q.get("option_b",""),
                "C": q.get("option_c",""), "D": q.get("option_d","")}
        expl = q.get("explanation", "")
        fb = (
            f"❌ خطأ.\nالجواب الصحيح: {cl}) {opts.get(cl,'')}"
            f"{chr(10) + chr(10) + '💡 ' + expl if expl else ''}"
        )

    state["current"] += 1
    await update.message.reply_text(fb)
    await asyncio.sleep(1.5)
    await _send_normal_question(chat_id, context)


# ─────────────────────────────────────────
# معالجة إجابة — وضع الرسمات
# ─────────────────────────────────────────

async def _handle_drawing_answer(chat_id, context, update, text, state) -> None:
    d_idx    = state["drawing_idx"]
    q_idx    = state["q_in_drawing"]
    drawings = state["drawings"]

    if d_idx >= len(drawings):
        await finish_quiz(chat_id, context)
        return

    drawing = drawings[d_idx]
    qs      = drawing["questions"]
    q       = qs[q_idx]

    correct = (q.get("answer") or q.get("correct_answer", "")).lower().strip()
    given   = ANSWER_MAP.get(text.lower(), text.lower()[:1])
    is_correct = given == correct

    await record_answer(
        session_id=state["session_id"],
        user_id=state["user_id"],
        question_id=q.get("id", 0),
        user_answer=given,
        is_correct=is_correct,
    )

    if is_correct:
        state["score"] += 1
        fb = "✅ صحيح!"
    else:
        cl   = correct.upper()
        opts = {"A": q.get("option_a",""), "B": q.get("option_b",""),
                "C": q.get("option_c",""), "D": q.get("option_d","")}
        fb = f"❌ خطأ.\nالجواب الصحيح: {cl}) {opts.get(cl,'')}"

    await update.message.reply_text(fb)
    await asyncio.sleep(1.2)

    # الانتقال للسؤال التالي
    state["q_in_drawing"] += 1

    # هل انتهت أسئلة هذه الرسمة؟
    if state["q_in_drawing"] >= len(qs):
        # ─── انتهت أسئلة الرسمة الحالية ────────────
        score_this = sum(
            1 for _ in range(len(qs))   # نحتاج تتبع نتيجة كل رسمة لاحقاً
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ انتهت أسئلة الرسمة {drawing['num']}: {drawing['title']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            ),
        )

        # الانتقال للرسمة التالية
        state["drawing_idx"]  += 1
        state["q_in_drawing"]  = 0

        await asyncio.sleep(1.5)

        next_idx = state["drawing_idx"]
        if next_idx >= len(drawings):
            # كل الرسمات انتهت
            await finish_quiz(chat_id, context)
        else:
            # إعلان الرسمة التالية
            next_drawing = drawings[next_idx]
            await _announce_drawing(chat_id, context, next_drawing)
            await asyncio.sleep(1.0)
            await _send_drawing_question(chat_id, context)
    else:
        # سؤال تالٍ في نفس الرسمة
        await _send_drawing_question(chat_id, context)


# ═══════════════════════════════════════════════════════════
# نقطة الدخول
# ═══════════════════════════════════════════════════════════

def main() -> None:
    logger.info("🚀 بدء تشغيل البوت...")
    logger.info(f"BOT_TOKEN موجود: {'نعم' if BOT_TOKEN else 'لا'}")
    logger.info(f"DATABASE_URL موجود: {'نعم' if os.getenv('DATABASE_URL') else 'لا'}")

    logger.info("🔄 تهيئة قاعدة البيانات...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"⚠️ تعذّر الاتصال بقاعدة البيانات: {e}")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu",  menu_cmd))
    app.add_handler(CommandHandler("stop",  stop_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    # معالج شامل لكل الأزرار
    app.add_handler(CallbackQueryHandler(button_handler))

    # الرسائل النصية (الإجابات)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    logger.info("🚀 البوت يعمل الآن...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
