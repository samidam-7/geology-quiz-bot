"""
إدارة قاعدة البيانات - Neon.tech PostgreSQL
يتوافق مع المخطط الحالي للقاعدة
"""

import os
import logging
import asyncio
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from typing import Optional

logger = logging.getLogger(__name__)

# ==========================================
# الاتصال بقاعدة البيانات
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")

_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=5, dsn=DATABASE_URL)
    return _pool


def get_conn():
    return get_pool().getconn()


def release_conn(conn):
    get_pool().putconn(conn)


# ==========================================
# تهيئة الجداول (تأكد من وجودها فقط)
# ==========================================
def init_db() -> None:
    """التأكد من وجود جميع الجداول المطلوبة"""
    if not DATABASE_URL:
        logger.warning("⚠️ DATABASE_URL غير مضبوط — سيعمل البوت بدون قاعدة بيانات")
        return

    # جدول المستخدمين
    sql_users = """
    CREATE TABLE IF NOT EXISTS users (
        user_id    BIGINT PRIMARY KEY,
        username   VARCHAR(255),
        first_name VARCHAR(255),
        last_name  VARCHAR(255),
        created_at TIMESTAMP DEFAULT NOW()
    );"""

    # جدول جلسات الاختبار
    sql_sessions = """
    CREATE TABLE IF NOT EXISTS quiz_sessions (
        id               SERIAL PRIMARY KEY,
        user_id          BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        subject          VARCHAR(255) NOT NULL,
        total_questions  INT DEFAULT 0,
        correct_answers  INT DEFAULT 0,
        wrong_answers    INT DEFAULT 0,
        is_review        BOOLEAN DEFAULT FALSE,
        is_completed     BOOLEAN DEFAULT FALSE,
        start_time       TIMESTAMP DEFAULT NOW(),
        end_time         TIMESTAMP
    );"""

    # جدول إجابات الاختبار
    sql_answers = """
    CREATE TABLE IF NOT EXISTS quiz_answers (
        id          SERIAL PRIMARY KEY,
        session_id  INT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
        question_id INT NOT NULL,
        user_answer CHAR(1),
        is_correct  BOOLEAN,
        answered_at TIMESTAMP DEFAULT NOW()
    );"""

    # جدول الأخطاء المتكررة
    sql_mistakes = """
    CREATE TABLE IF NOT EXISTS user_mistakes (
        user_id       BIGINT NOT NULL,
        question_id   INT NOT NULL,
        wrong_count   INT DEFAULT 1,
        last_wrong_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (user_id, question_id)
    );"""

    # جدول الموضوع المعلّق
    sql_pending = """
    CREATE TABLE IF NOT EXISTS user_pending_subject (
        user_id    BIGINT PRIMARY KEY,
        subject    VARCHAR(255),
        updated_at TIMESTAMP DEFAULT NOW()
    );"""

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql_users)
            cur.execute(sql_sessions)
            cur.execute(sql_answers)
            cur.execute(sql_mistakes)
            cur.execute(sql_pending)
        conn.commit()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# تسجيل المستخدم (أو تحديث بياناته)
# ==========================================
async def register_user(user_id: int, username: str, first_name: str, last_name: str = "") -> None:
    if not DATABASE_URL:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _register_user_sync, user_id, username, first_name, last_name)


def _register_user_sync(user_id, username, first_name, last_name):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (user_id, username, first_name, last_name)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE
                   SET username=EXCLUDED.username,
                       first_name=EXCLUDED.first_name,
                       last_name=EXCLUDED.last_name""",
                (user_id, username or "", first_name or "", last_name or ""),
            )
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في تسجيل المستخدم: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# جلب الأسئلة حسب الموضوع (subject)
# ==========================================
async def get_questions_by_subject(subject: str, limit: int = 0) -> list:
    """
    جلب أسئلة موضوع معين.
    المخطط الحالي: subject, question_text, option_a..d, correct_answer
    """
    if not DATABASE_URL:
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_questions_sync, subject, limit)


def _fetch_questions_sync(subject: str, limit: int = 0) -> list:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if limit > 0:
                cur.execute(
                    """SELECT id, subject, question_text AS question,
                              option_a, option_b, option_c, option_d,
                              correct_answer AS answer, priority
                       FROM questions
                       WHERE subject = %s
                       ORDER BY priority DESC, RANDOM()
                       LIMIT %s""",
                    (subject, limit),
                )
            else:
                cur.execute(
                    """SELECT id, subject, question_text AS question,
                              option_a, option_b, option_c, option_d,
                              correct_answer AS answer, priority
                       FROM questions
                       WHERE subject = %s
                       ORDER BY priority DESC, id""",
                    (subject,),
                )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب أسئلة '{subject}': {e}")
        return []
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# جلب أسئلة الأخطاء المتكررة للمستخدم
# ==========================================
async def get_user_mistakes(user_id: int, subject: str = None) -> list:
    if not DATABASE_URL:
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_mistakes_sync, user_id, subject)


def _fetch_mistakes_sync(user_id: int, subject: str = None) -> list:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if subject:
                cur.execute(
                    """SELECT q.id, q.question_text AS question,
                              q.option_a, q.option_b, q.option_c, q.option_d,
                              q.correct_answer AS answer, um.wrong_count
                       FROM user_mistakes um
                       JOIN questions q ON q.id = um.question_id
                       WHERE um.user_id = %s AND q.subject = %s
                       ORDER BY um.wrong_count DESC""",
                    (user_id, subject),
                )
            else:
                cur.execute(
                    """SELECT q.id, q.question_text AS question,
                              q.option_a, q.option_b, q.option_c, q.option_d,
                              q.correct_answer AS answer, um.wrong_count, q.subject
                       FROM user_mistakes um
                       JOIN questions q ON q.id = um.question_id
                       WHERE um.user_id = %s
                       ORDER BY um.wrong_count DESC""",
                    (user_id,),
                )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"خطأ في جلب أخطاء المستخدم: {e}")
        return []
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# إنشاء جلسة اختبار جديدة
# ==========================================
async def create_session(user_id: int, subject: str, total: int, is_review: bool = False) -> int:
    if not DATABASE_URL:
        return -1
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _create_session_sync, user_id, subject, total, is_review)


def _create_session_sync(user_id, subject, total, is_review) -> int:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO quiz_sessions (user_id, subject, total_questions, is_review)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (user_id, subject, total, is_review),
            )
            session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
    except Exception as e:
        logger.error(f"خطأ في إنشاء الجلسة: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# تسجيل إجابة المستخدم وتحديث الجلسة
# ==========================================
async def record_answer(
    session_id: int,
    user_id: int,
    question_id: int,
    user_answer: str,
    is_correct: bool,
) -> None:
    if not DATABASE_URL or session_id < 0:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, _record_answer_sync, session_id, user_id, question_id, user_answer, is_correct
    )


def _record_answer_sync(session_id, user_id, question_id, user_answer, is_correct):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # تسجيل الإجابة
            cur.execute(
                """INSERT INTO quiz_answers (session_id, question_id, user_answer, is_correct)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, question_id, user_answer[:1] if user_answer else "", is_correct),
            )
            # تحديث إحصائيات الجلسة
            if is_correct:
                cur.execute(
                    "UPDATE quiz_sessions SET correct_answers = correct_answers + 1 WHERE id = %s",
                    (session_id,),
                )
            else:
                cur.execute(
                    "UPDATE quiz_sessions SET wrong_answers = wrong_answers + 1 WHERE id = %s",
                    (session_id,),
                )
                # تسجيل الخطأ في جدول user_mistakes
                cur.execute(
                    """INSERT INTO user_mistakes (user_id, question_id, wrong_count, last_wrong_at)
                       VALUES (%s, %s, 1, NOW())
                       ON CONFLICT (user_id, question_id)
                       DO UPDATE SET wrong_count = user_mistakes.wrong_count + 1,
                                     last_wrong_at = NOW()""",
                    (user_id, question_id),
                )
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في تسجيل الإجابة: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# إغلاق الجلسة عند انتهاء الاختبار
# ==========================================
async def close_session(session_id: int) -> None:
    if not DATABASE_URL or session_id < 0:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _close_session_sync, session_id)


def _close_session_sync(session_id: int):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE quiz_sessions
                   SET is_completed = TRUE, end_time = NOW()
                   WHERE id = %s""",
                (session_id,),
            )
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في إغلاق الجلسة: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# إحصائيات المستخدم
# ==========================================
async def get_user_stats(user_id: int) -> dict:
    if not DATABASE_URL:
        return {}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_user_stats_sync, user_id)


def _get_user_stats_sync(user_id: int) -> dict:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """SELECT
                     COUNT(*) AS sessions,
                     SUM(correct_answers) AS total_correct,
                     SUM(wrong_answers) AS total_wrong,
                     SUM(total_questions) AS total_q
                   FROM quiz_sessions
                   WHERE user_id = %s AND is_completed = TRUE""",
                (user_id,),
            )
            row = dict(cur.fetchone())

            # عدد الأخطاء المتراكمة
            cur.execute(
                "SELECT COUNT(*) AS mistake_count FROM user_mistakes WHERE user_id = %s",
                (user_id,),
            )
            row["mistakes"] = cur.fetchone()[0]
        return row
    except Exception as e:
        logger.error(f"خطأ في إحصائيات المستخدم: {e}")
        return {}
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# قائمة المتصدرين
# ==========================================
async def get_leaderboard(limit: int = 10) -> list:
    if not DATABASE_URL:
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_leaderboard_sync, limit)


def _get_leaderboard_sync(limit: int) -> list:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """SELECT
                     qs.user_id,
                     u.first_name,
                     u.username,
                     SUM(qs.correct_answers) AS total_correct,
                     SUM(qs.total_questions) AS total_q,
                     COUNT(*) AS sessions
                   FROM quiz_sessions qs
                   LEFT JOIN users u ON u.user_id = qs.user_id
                   WHERE qs.is_completed = TRUE
                   GROUP BY qs.user_id, u.first_name, u.username
                   ORDER BY total_correct DESC
                   LIMIT %s""",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"خطأ في المتصدرين: {e}")
        return []
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# حفظ / جلب الموضوع المعلّق
# ==========================================
async def save_pending_subject(user_id: int, subject: str) -> None:
    if not DATABASE_URL:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_pending_sync, user_id, subject)


def _save_pending_sync(user_id: int, subject: str):
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO user_pending_subject (user_id, subject, updated_at)
                   VALUES (%s, %s, NOW())
                   ON CONFLICT (user_id) DO UPDATE
                   SET subject = EXCLUDED.subject, updated_at = NOW()""",
                (user_id, subject),
            )
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في حفظ الموضوع المعلّق: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


async def get_pending_subject(user_id: int) -> Optional[str]:
    if not DATABASE_URL:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_pending_sync, user_id)


def _get_pending_sync(user_id: int) -> Optional[str]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subject FROM user_pending_subject WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"خطأ في جلب الموضوع المعلّق: {e}")
        return None
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# عدد الأسئلة لكل موضوع
# ==========================================
async def get_subject_counts() -> dict:
    if not DATABASE_URL:
        return {}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_counts_sync)


def _get_counts_sync() -> dict:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT subject, COUNT(*) FROM questions GROUP BY subject")
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"خطأ في جلب الإحصائيات: {e}")
        return {}
    finally:
        if conn:
            release_conn(conn)
