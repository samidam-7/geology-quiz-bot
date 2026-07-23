"""
إدارة قاعدة البيانات - Neon.tech PostgreSQL
يدعم: تهيئة الجداول، جلب الأسئلة، حفظ النتائج
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
# اتصال قاعدة البيانات
# ==========================================
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("NEON_DATABASE_URL")
)

_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=DATABASE_URL,
        )
    return _pool


def get_conn():
    return get_pool().getconn()


def release_conn(conn):
    get_pool().putconn(conn)


# ==========================================
# تهيئة الجداول
# ==========================================
def init_db() -> None:
    """إنشاء الجداول إذا لم تكن موجودة"""
    if not DATABASE_URL:
        logger.warning("⚠️ DATABASE_URL غير مضبوط — البوت يعمل بدون قاعدة بيانات")
        return

    sql_questions = """
    CREATE TABLE IF NOT EXISTS questions (
        id          SERIAL PRIMARY KEY,
        category    TEXT    NOT NULL,
        question    TEXT    NOT NULL,
        option_a    TEXT,
        option_b    TEXT,
        option_c    TEXT,
        option_d    TEXT,
        answer      TEXT    NOT NULL,
        explanation TEXT,
        created_at  TIMESTAMP DEFAULT NOW()
    );
    """

    sql_scores = """
    CREATE TABLE IF NOT EXISTS scores (
        id         SERIAL PRIMARY KEY,
        user_id    BIGINT  NOT NULL,
        category   TEXT    NOT NULL,
        score      INT     NOT NULL,
        total      INT     NOT NULL,
        percent    NUMERIC(5,2),
        played_at  TIMESTAMP DEFAULT NOW()
    );
    """

    sql_index_category = """
    CREATE INDEX IF NOT EXISTS idx_questions_category
        ON questions(category);
    """

    sql_index_user = """
    CREATE INDEX IF NOT EXISTS idx_scores_user
        ON scores(user_id);
    """

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(sql_questions)
            cur.execute(sql_scores)
            cur.execute(sql_index_category)
            cur.execute(sql_index_user)
        conn.commit()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
        _seed_if_empty(conn)
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# إضافة أسئلة تجريبية إذا كانت الجداول فارغة
# ==========================================
def _seed_if_empty(conn) -> None:
    """يضيف أسئلة أولية إذا كانت قاعدة البيانات فارغة"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM questions")
        count = cur.fetchone()[0]

    if count > 0:
        logger.info(f"ℹ️ قاعدة البيانات تحتوي على {count} سؤال — لا حاجة للبذر")
        return

    logger.info("🌱 إضافة الأسئلة الأولية...")

    questions_data = [
        # ============================================================
        # فئة: geology (زمین‌شناسی)
        # ============================================================
        ("geology", "۱. طبق تعریف دقیق جزوه، کدام مورد 'کانی' محسوب می‌شود؟\nأ) نفت خام\nب) شیشه (Obsidian)\nج) یخ طبیعی\nد) مروارید", "نفت خام", "شیشه (Obsidian)", "یخ طبیعی", "مروارید", "ج", "کانی باید جامد، طبیعی و دارای ساختار بلوری باشد. یخ طبیعی تمام شروط کانی بودن را دارد."),
        ("geology", "۲. کانی‌ها در چند سیستم بلوری متبلور می‌شوند؟\nأ) ۶ سیستم\nب) ۷ سیستم\nج) ۵ سیستم\nد) ۸ سیستم", "۶ سیستم", "۷ سیستم", "۵ سیستم", "۸ سیستم", "ب", "سیستم‌های تبلور ۷ مورد هستند: کوبیک، تتراگونال، اورتورومبیک، مونوکلینیک، تریکلینیک، هگزاگونال و تریگونال."),
        ("geology", "۳. نقش اصلی آب (H2O) در ماگما چیست؟\nأ) افزایش نقطه ذوب\nب) کاهش نقطه ذوب و کاهش ویسکوزیته\nج) افزایش ویسکوزیته\nد) جلوگیری از تبلور", "افزایش نقطه ذوب", "کاهش نقطه ذوب و کاهش ویسکوزیته", "افزایش ویسکوزیته", "جلوگیری از تبلور", "ب", "آب باعث شکسته شدن پیوندهای سیلیکاتی می‌شود، بنابراین هم دمای ذوب سنگ را پایین می‌آورد و هم ویسکوزیته را کاهش می‌دهد."),
        ("geology", "۴. کدام عناصر باعث 'افزایش' ویسکوزیته ماگما می‌شوند؟\nأ) آهن و منیزیم\nب) سدیم و پتاسیم\nج) سیلیس و آلومینیوم\nد) کلسیم و آهن", "آهن و منیزیم", "سدیم و پتاسیم", "سیلیس و آلومینیوم", "کلسیم و آهن", "ج", "سیلیس (SiO2) و آلومینیوم (Al) باعث پلیمری شدن ماگما و افزایش غلظت می‌شوند."),
        ("geology", "۵. اگر ماگما ۹۵٪ گاز داشته باشد، فوران چگونه خواهد بود؟\nأ) آرام و روان\nب) تشکیل گنبد گدازه\nج) شدیداً انفجاری\nد) تشکیل دایک", "آرام و روان", "تشکیل گنبد گدازه", "شدیداً انفجاری", "تشکیل دایک", "ج", "اگر درصد گاز ماگما بسیار بالا (۹۵٪) باشد، فوران به صورت انفجاری رخ می‌دهد."),
        # ============================================================
        # فئة: animal_1 (حيوان الجزء الأول)
        # ============================================================
        ("animal_1", "ما هو أكبر الثدييات في العالم؟\nأ) الفيل الأفريقي\nب) الحوت الأزرق\nج) الزرافة\nد) وحيد القرن", "الفيل الأفريقي", "الحوت الأزرق", "الزرافة", "وحيد القرن", "ب", "الحوت الأزرق هو أكبر حيوان على وجه الأرض، يصل طوله إلى 30 متراً ووزنه إلى 180 طناً."),
        ("animal_1", "ما هو الحيوان الذي لا ينام أبداً؟\nأ) القرش\nب) الدلفين\nج) الضفدع\nد) الحمام", "القرش", "الدلفين", "الضفدع", "الحمام", "أ", "القرش يجب أن يستمر في الحركة طوال الوقت ليتنفس، لذلك لا ينام كما تنام الحيوانات الأخرى."),
        ("animal_1", "كم عدد قلوب الأخطبوط؟\nأ) قلب واحد\nب) قلبان\nج) ثلاثة قلوب\nد) أربعة قلوب", "قلب واحد", "قلبان", "ثلاثة قلوب", "أربعة قلوب", "ج", "للأخطبوط ثلاثة قلوب: قلبان يضخان الدم عبر الخياشيم وقلب رئيسي يضخ الدم عبر الجسم."),
        ("animal_1", "أي الحيوانات الآتية يمكنها رؤية الألوان؟\nأ) الكلاب\nب) القطط\nج) فراشة الملك\nد) الأبقار", "الكلاب", "القطط", "فراشة الملك", "الأبقار", "ج", "فراشة الملك (Monarch) تمتلك أعيناً مركبة تستطيع رؤية طيف واسع من الألوان بما في ذلك فوق البنفسجي."),
        ("animal_1", "ما هو الحيوان الأسرع على الأرض؟\nأ) الأسد\nب) الحصان\nج) النمر\nد) الفهد", "الأسد", "الحصان", "النمر", "الفهد", "د", "الفهد هو أسرع الحيوانات البرية، يصل سرعته إلى 120 كم/ساعة على مسافات قصيرة."),
        # ============================================================
        # فئة: animal_2 (حيوان الجزء الثاني) — هذه الفئة كانت تظهر فارغة
        # ============================================================
        ("animal_2", "ما هو الحيوان الذي يمكنه العيش أطول فترة بدون ماء؟\nأ) الجمل\nب) الكنغر الجرذي\nج) الضبة\nد) الغزال", "الجمل", "الكنغر الجرذي", "الضبة", "الغزال", "ب", "الكنغر الجرذي (Kangaroo Rat) يحصل على كل احتياجاته من الماء من الغذاء فقط ولا يحتاج للشرب طوال حياته."),
        ("animal_2", "كم عدد أسنان الحلزون؟\nأ) لا أسنان\nب) حتى 10 أسنان\nج) مئات الأسنان\nد) أكثر من 10,000 سن", "لا أسنان", "حتى 10 أسنان", "مئات الأسنان", "أكثر من 10,000 سن", "د", "يمتلك الحلزون أكثر من 14,000 سن صغيرة جداً على لسانه (الريدولا) يستخدمها لتقطيع الطعام."),
        ("animal_2", "أي الحيوانات الآتية لها ذاكرة أطول؟\nأ) الأسماك الذهبية\nب) الفيل\nج) القرد\nد) الحمامة", "الأسماك الذهبية", "الفيل", "القرد", "الحمامة", "ب", "الفيل يمتلك ذاكرة استثنائية، يتذكر أفراد قطيعه وأماكن المياه حتى بعد عقود من الزمن."),
        ("animal_2", "ما هو الحيوان الوحيد الذي لا يتراجع؟\nأ) الدب القطبي\nب) الكنغر\nج) الحصان\nد) النمر الثلجي", "الدب القطبي", "الكنغر", "الحصان", "النمر الثلجي", "ب", "الكنغر لا يستطيع المشي للخلف بسبب بنية ذيله وساقيه الخلفيتين الكبيرتين."),
        ("animal_2", "كم عام يمكن أن يعيش السلحفاة العملاقة؟\nأ) 50 سنة\nب) 80 سنة\nج) 100 سنة\nد) أكثر من 150 سنة", "50 سنة", "80 سنة", "100 سنة", "أكثر من 150 سنة", "د", "السلحفاة العملاقة من أطول الحيوانات عمراً، وقد وثّق العلماء أعماراً تتجاوز 180 عاماً."),
    ]

    insert_sql = """
    INSERT INTO questions
        (category, question, option_a, option_b, option_c, option_d, answer, explanation)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, insert_sql, questions_data)
        conn.commit()
        logger.info(f"✅ تم إضافة {len(questions_data)} سؤال بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة الأسئلة: {e}")
        conn.rollback()


# ==========================================
# جلب الأسئلة حسب الفئة
# ==========================================
async def get_questions_by_category(category: str) -> list:
    """جلب جميع أسئلة فئة معينة من قاعدة البيانات"""
    if not DATABASE_URL:
        return _get_fallback_questions(category)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_questions_sync, category)


def _fetch_questions_sync(category: str) -> list:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM questions WHERE category = %s ORDER BY id",
                (category,),
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب أسئلة '{category}': {e}")
        return _get_fallback_questions(category)
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# أسئلة احتياطية (إذا لم تتوفر قاعدة البيانات)
# ==========================================
def _get_fallback_questions(category: str) -> list:
    """أسئلة احتياطية تُستخدم إذا لم تكن قاعدة البيانات متاحة"""
    fallback = {
        "geology": [
            {"question": "ما هو أصلب المعادن؟\nأ) الكوارتز\nب) الحديد\nج) الماس\nد) الكوراندوم", "answer": "ج", "explanation": "الماس هو أصلب المعادن الطبيعية على مقياس موس (درجة 10)."},
        ],
        "animal_1": [
            {"question": "ما هو أكبر الثدييات في العالم؟\nأ) الفيل\nب) الحوت الأزرق\nج) الزرافة\nد) وحيد القرن", "answer": "ب", "explanation": "الحوت الأزرق هو أكبر حيوان على وجه الأرض."},
        ],
        "animal_2": [
            {"question": "ما هو الحيوان الذي يمكنه العيش أطول فترة بدون ماء؟\nأ) الجمل\nب) الكنغر الجرذي\nج) الضبة\nد) الغزال", "answer": "ب", "explanation": "الكنغر الجرذي يحصل على الماء من غذائه فقط."},
        ],
    }
    return fallback.get(category, [])


# ==========================================
# حفظ نتيجة المستخدم
# ==========================================
async def save_score(user_id: int, category: str, score: int, total: int) -> None:
    if not DATABASE_URL:
        return

    percent = round((score / total) * 100, 2) if total > 0 else 0
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_score_sync, user_id, category, score, total, percent)


def _save_score_sync(user_id: int, category: str, score: int, total: int, percent: float) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scores (user_id, category, score, total, percent)
                   VALUES (%s, %s, %s, %s, %s)""",
                (user_id, category, score, total, percent),
            )
        conn.commit()
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ النتيجة: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            release_conn(conn)


# ==========================================
# جلب قائمة المتصدرين
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
                """SELECT user_id, category, MAX(score) AS score, total
                   FROM scores
                   GROUP BY user_id, category, total
                   ORDER BY score DESC
                   LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المتصدرين: {e}")
        return []
    finally:
        if conn:
            release_conn(conn)
