"""بوت Telegram تعليمي للبحث في القرآن وشرح أحكام التجويد."""

from __future__ import annotations

import html
import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from tajweed import analyse_tajweed, normalize_arabic


ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "quran.json"
TELEGRAM_LIMIT = 4096
DEFAULT_QURAN_API = "https://api.alquran.cloud/v1"
TAFSIR_API = "https://alfurqan.online/api/v1/tafseer"


def quran_api() -> str:
    return os.getenv("QURAN_API_URL", DEFAULT_QURAN_API).rstrip("/")

SURAH_META = [
    ("الفاتحة", "مكية"), ("البقرة", "مدنية"), ("آل عمران", "مدنية"),
    ("النساء", "مدنية"), ("المائدة", "مدنية"), ("الأنعام", "مكية"),
    ("الأعراف", "مكية"), ("الأنفال", "مدنية"), ("التوبة", "مدنية"),
    ("يونس", "مكية"), ("هود", "مكية"), ("يوسف", "مكية"),
    ("الرعد", "مدنية"), ("إبراهيم", "مكية"), ("الحجر", "مكية"),
    ("النحل", "مكية"), ("الإسراء", "مكية"), ("الكهف", "مكية"),
    ("مريم", "مكية"), ("طه", "مكية"), ("الأنبياء", "مكية"),
    ("الحج", "مدنية"), ("المؤمنون", "مكية"), ("النور", "مدنية"),
    ("الفرقان", "مكية"), ("الشعراء", "مكية"), ("النمل", "مكية"),
    ("القصص", "مكية"), ("العنكبوت", "مكية"), ("الروم", "مكية"),
    ("لقمان", "مكية"), ("السجدة", "مكية"), ("الأحزاب", "مدنية"),
    ("سبأ", "مكية"), ("فاطر", "مكية"), ("يس", "مكية"),
    ("الصافات", "مكية"), ("ص", "مكية"), ("الزمر", "مكية"),
    ("غافر", "مكية"), ("فصلت", "مكية"), ("الشورى", "مكية"),
    ("الزخرف", "مكية"), ("الدخان", "مكية"), ("الجاثية", "مكية"),
    ("الأحقاف", "مكية"), ("محمد", "مدنية"), ("الفتح", "مدنية"),
    ("الحجرات", "مدنية"), ("ق", "مكية"), ("الذاريات", "مكية"),
    ("الطور", "مكية"), ("النجم", "مكية"), ("القمر", "مكية"),
    ("الرحمن", "مدنية"), ("الواقعة", "مكية"), ("الحديد", "مدنية"),
    ("المجادلة", "مدنية"), ("الحشر", "مدنية"), ("الممتحنة", "مدنية"),
    ("الصف", "مدنية"), ("الجمعة", "مدنية"), ("المنافقون", "مدنية"),
    ("التغابن", "مدنية"), ("الطلاق", "مدنية"), ("التحريم", "مدنية"),
    ("الملك", "مكية"), ("القلم", "مكية"), ("الحاقة", "مكية"),
    ("المعارج", "مكية"), ("نوح", "مكية"), ("الجن", "مكية"),
    ("المزمل", "مكية"), ("المدثر", "مكية"), ("القيامة", "مكية"),
    ("الإنسان", "مدنية"), ("المرسلات", "مكية"), ("النبأ", "مكية"),
    ("النازعات", "مكية"), ("عبس", "مكية"), ("التكوير", "مكية"),
    ("الانفطار", "مكية"), ("المطففين", "مكية"), ("الانشقاق", "مكية"),
    ("البروج", "مكية"), ("الطارق", "مكية"), ("الأعلى", "مكية"),
    ("الغاشية", "مكية"), ("الفجر", "مكية"), ("البلد", "مكية"),
    ("الشمس", "مكية"), ("الليل", "مكية"), ("الضحى", "مكية"),
    ("الشرح", "مكية"), ("التين", "مكية"), ("العلق", "مكية"),
    ("القدر", "مكية"), ("البينة", "مدنية"), ("الزلزلة", "مدنية"),
    ("العاديات", "مكية"), ("القارعة", "مكية"), ("التكاثر", "مكية"),
    ("العصر", "مكية"), ("الهمزة", "مكية"), ("الفيل", "مكية"),
    ("قريش", "مكية"), ("الماعون", "مكية"), ("الكوثر", "مكية"),
    ("الكافرون", "مكية"), ("النصر", "مدنية"), ("المسد", "مكية"),
    ("الإخلاص", "مكية"), ("الفلق", "مكية"), ("الناس", "مكية"),
]

# المعرّفات موثقة ضمن إصدارات الصوت في Al Quran Cloud.
RECITERS = {
    "ar.alafasy": "مشاري راشد العفاسي",
    "ar.husary": "محمود خليل الحصري",
    "ar.minshawi": "محمد صديق المنشاوي",
    "ar.abdulbasitmurattal": "عبد الباسط عبد الصمد — مرتل",
    "ar.abdurrahmaansudais": "عبد الرحمن السديس",
    "ar.mahermuaiqly": "ماهر المعيقلي",
    "ar.hudhaify": "علي الحذيفي",
    "ar.muhammadjibreel": "محمد جبريل",
    "ar.muhammadayyoub": "محمد أيوب",
}

TAFSIRS = {
    "muyassar": "التفسير الميسّر",
    "al-saddi": "تفسير السعدي",
    "al-tabari": "تفسير الطبري",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def western_digits(text: str) -> str:
    return text.translate(ARABIC_DIGITS)


def parse_surah_reference(text: str) -> tuple[int, int] | None:
    """يفهم مثل: البقرة 255، سورة البقره آية ٢٥٥، وآل عمران: 10."""
    cleaned = western_digits(text)
    numbers = re.findall(r"\d{1,3}", cleaned)
    if not numbers:
        return None
    verse = int(numbers[-1])
    name_text = re.sub(r"\d{1,3}", " ", cleaned)
    name_text = re.sub(
        r"\b(?:سورة|سوره|آية|اية|ايه|الآية|الايه|رقم)\b",
        " ",
        name_text,
    )
    name_text = normalize_arabic(name_text)
    if not name_text:
        return None
    scored = [
        (
            SequenceMatcher(None, name_text, normalize_arabic(name)).ratio(),
            index + 1,
        )
        for index, (name, _) in enumerate(SURAH_META)
    ]
    score, surah = max(scored)
    return (surah, verse) if score >= 0.55 else None


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 35) -> Any:
    headers = {"User-Agent": "TajweedTelegramBot/1.0"}
    if payload is None:
        response = requests.get(url, headers=headers, timeout=(5, timeout))
    else:
        response = requests.post(url, json=payload, headers=headers, timeout=(5, timeout))
    response.raise_for_status()
    return response.json()


class QuranStore:
    def __init__(self) -> None:
        self.ayahs: list[dict[str, Any]] = []

    def load(self) -> None:
        if CACHE_FILE.exists():
            self.ayahs = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        else:
            logging.info("تنزيل نص القرآن لأول تشغيل...")
            response = request_json(f"{quran_api()}/quran/quran-uthmani")
            chapters = response["data"]["surahs"]
            self.ayahs = [
                {
                    "number": ayah["number"],
                    "surah": chapter["number"],
                    "ayah": ayah["numberInSurah"],
                    "text": ayah["text"],
                }
                for chapter in chapters for ayah in chapter["ayahs"]
            ]
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(
                json.dumps(self.ayahs, ensure_ascii=False), encoding="utf-8"
            )
        for item in self.ayahs:
            item["_search"] = normalize_arabic(item["text"])
            item["_search_expanded"] = normalize_arabic(
                item["text"], expand_dagger_alif=True
            )
        logging.info("تم تجهيز %s آية", len(self.ayahs))

    def find(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        needle = normalize_arabic(query)
        if len(needle.replace(" ", "")) < 3:
            return []
        exact = [
            a for a in self.ayahs
            if needle in {a["_search"], a["_search_expanded"]}
        ]
        partial = [
            a for a in self.ayahs
            if (
                needle in a["_search"]
                or needle in a["_search_expanded"]
            ) and a not in exact
        ]
        matches = exact + partial
        if matches:
            return matches[:limit]

        # عند وجود خطأ إملائي نقارن العبارة بنوافذ كلمات مساوية لطولها.
        query_words = needle.split()
        window_size = max(1, len(query_words))
        fuzzy: list[tuple[float, dict[str, Any]]] = []
        for ayah in self.ayahs:
            words = ayah["_search_expanded"].split()
            best = max(
                (
                    SequenceMatcher(
                        None, needle, " ".join(words[index:index + window_size])
                    ).ratio()
                    for index in range(max(1, len(words) - window_size + 1))
                ),
                default=0.0,
            )
            if best >= 0.68:
                fuzzy.append((best, ayah))
        fuzzy.sort(key=lambda item: item[0], reverse=True)
        return [ayah for _, ayah in fuzzy[:limit]]

    def by_number(self, number: int) -> dict[str, Any] | None:
        return next((a for a in self.ayahs if a["number"] == number), None)


class Bot:
    def __init__(self, token: str, quran: QuranStore) -> None:
        self.base = f"https://api.telegram.org/bot{token}"
        self.quran = quran
        self.offset = 0
        self.preferred_reciter: dict[int, str] = {}
        # الطلبات البطيئة لا توقف استقبال الرسائل الجديدة.
        self.workers = ThreadPoolExecutor(max_workers=6, thread_name_prefix="bot-worker")
        # إرسال الردود ومعالجة الأزرار يجريان بالتوازي مع polling لواجهة تيليجرام.
        self.update_workers = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="update-worker"
        )
        self.telegram_session = requests.Session()
        self.telegram_session.headers.update({"User-Agent": "TajweedTelegramBot/1.0"})
        self.telegram_session.mount(
            "https://",
            HTTPAdapter(pool_connections=4, pool_maxsize=12, max_retries=1),
        )
        self.tafsir_cache: dict[tuple[int, str], str] = {}
        self.audio_cache: dict[tuple[int, str], str] = {}
        self.cache_lock = Lock()

    def api(self, method: str, **payload: Any) -> Any:
        # الجلسة تعيد استخدام اتصال TLS بدل إنشاء اتصال جديد لكل رسالة.
        read_timeout = 35 if method == "getUpdates" else 15
        response = self.telegram_session.post(
            f"{self.base}/{method}",
            json=payload,
            timeout=(4, read_timeout),
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", "Telegram API error"))
        return result["result"]

    def send(self, chat_id: int, text: str, keyboard: list[list[dict[str, str]]] | None = None) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:TELEGRAM_LIMIT],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        self.api("sendMessage", **payload)

    def action(self, chat_id: int, action: str = "typing") -> None:
        """يعرض للمستخدم حالة فورية، ولا يجعل فشلها يفشل الطلب الأساسي."""
        try:
            self.api("sendChatAction", chat_id=chat_id, action=action)
        except Exception:
            logging.debug("تعذر إرسال حالة المحادثة", exc_info=True)

    def background(self, function: Any, *args: Any) -> None:
        future = self.workers.submit(function, *args)
        self._report_background_failure(future)

    def dispatch(self, function: Any, *args: Any) -> None:
        """يعالج التحديث دون تعطيل استقبال بقية رسائل تيليجرام."""
        future = self.update_workers.submit(function, *args)
        self._report_background_failure(future)

    @staticmethod
    def _report_background_failure(future: Any) -> None:
        def report_failure(done: Any) -> None:
            error = done.exception()
            if error:
                logging.error(
                    "فشلت مهمة خلفية",
                    exc_info=(type(error), error, error.__traceback__),
                )

        future.add_done_callback(report_failure)

    def welcome(self, chat_id: int) -> None:
        self.send(
            chat_id,
            "السلام عليكم ورحمة الله 🌿\n\n"
            "أرسل آية أو جزءًا منها، وسأعرض موضعها وأحكام التجويد "
            "وخيارات التفسير وإمكانية الاستماع.\n\n"
            "يمكنك أيضًا كتابة مرجع مثل: <b>2:255</b>\n"
            "القراءة المعتمدة حاليًا: <b>حفص عن عاصم</b>.\n"
            "استخدم /readers لعرض القرّاء المتاحين.",
            [[{"text": "🎲 آية عشوائية", "callback_data": "random"},
              {"text": "❓ المساعدة", "callback_data": "help"}]],
        )

    def help(self, chat_id: int) -> None:
        self.send(
            chat_id,
            "<b>طريقة الاستخدام</b>\n\n"
            "• أرسل: <code>من شر ما خلق</code>\n"
            "• أو المرجع: <code>113:2</code>\n"
            "• أو اسم السورة والآية: <code>البقرة 255</code>\n"
            "يدعم البوت الأرقام العربية والأخطاء الإملائية البسيطة، "
            "وسيطلب منك تأكيد الآية المقترحة.\n\n"
            "• استخدم /random لآية عشوائية.\n\n"
            "• استخدم /readers لاختيار القارئ المفضّل.\n\n"
            "التحليل آلي تعليمي، وقد تتأثر بعض الأحكام بطريقة الوصل والوقف؛ "
            "فلا يغني عن التلقي من معلّم متقن.",
        )

    def reciters_keyboard(self, number: int = 0) -> list[list[dict[str, str]]]:
        buttons = [
            {
                "text": f"🎙 {name}",
                "callback_data": f"play:{number}:{edition}",
            }
            for edition, name in RECITERS.items()
        ]
        return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]

    def show_reciters(self, chat_id: int, number: int = 0) -> None:
        action = "اختر القارئ لتشغيل الآية:" if number else "اختر قارئك المفضّل:"
        self.send(
            chat_id,
            f"<b>🎧 قائمة القرّاء</b>\n\n{action}\n"
            "سيُحفظ اختيارك طوال فترة تشغيل البوت.",
            self.reciters_keyboard(number),
        )

    def show_matches(self, chat_id: int, matches: list[dict[str, Any]]) -> None:
        if not matches:
            self.send(
                chat_id,
                "لم أستطع تحديد الآية بثقة. جرّب كتابة اسم السورة ورقم الآية "
                "مثل <code>البقرة 255</code>، أو أرسل ثلاث كلمات منها.",
            )
            return
        if len(matches) == 1:
            self.confirm_ayah(chat_id, matches[0])
            return
        buttons = []
        for ayah in matches:
            name = SURAH_META[ayah["surah"] - 1][0]
            buttons.append([{
                "text": f"{name} — الآية {ayah['ayah']}",
                "callback_data": f"candidate:{ayah['number']}",
            }])
        self.send(chat_id, "وجدت أكثر من نتيجة؛ اختر الآية الأقرب لما تقصده:", buttons)

    def confirm_ayah(self, chat_id: int, ayah: dict[str, Any]) -> None:
        name = SURAH_META[ayah["surah"] - 1][0]
        self.send(
            chat_id,
            "هل هذه هي الآية التي تقصدها؟\n\n"
            f"<b>﴿ {html.escape(ayah['text'])} ﴾</b>\n\n"
            f"سورة <b>{name}</b> — الآية <b>{ayah['ayah']}</b>",
            [[
                {
                    "text": "✅ نعم، صحيحة",
                    "callback_data": f"ayah:{ayah['number']}",
                },
                {"text": "❌ لا", "callback_data": "reject"},
            ]],
        )

    def show_ayah(self, chat_id: int, ayah: dict[str, Any]) -> None:
        name, revelation = SURAH_META[ayah["surah"] - 1]
        rules = analyse_tajweed(ayah["text"])
        rules_text = "\n".join(
            f"• <b>{html.escape(rule.name)}:</b> {html.escape(rule.explanation)}"
            for rule in rules[:12]
        ) or "• لم يكتشف التحليل الآلي حكمًا واضحًا في هذا الموضع."
        text = (
            f"<b>﴿ {html.escape(ayah['text'])} ﴾</b>\n\n"
            f"📖 سورة <b>{name}</b> ({revelation}) — الآية "
            f"<b>{ayah['ayah']}</b>\n\n"
            f"<b>أحكام التجويد الظاهرة:</b>\n{rules_text}\n\n"
            "⚠️ التحليل آلي تعليمي برواية حفص، ويراعى اختلاف الحكم عند "
            "الوصل والوقف. راجع معلّمًا متقنًا للتحقق."
        )
        number = ayah["number"]
        preferred = self.preferred_reciter.get(chat_id)
        audio_buttons = (
            [
                {"text": f"🎧 {RECITERS[preferred]}", "callback_data": f"play:{number}:{preferred}"},
                {"text": "🔄 قارئ آخر", "callback_data": f"audio:{number}"},
            ]
            if preferred
            else [{"text": "🎧 اختر القارئ", "callback_data": f"audio:{number}"}]
        )
        self.send(chat_id, text, [
            [{"text": "📚 اختر التفسير", "callback_data": f"tafsirs:{number}"}],
            audio_buttons,
            [{"text": "🧠 اختبرني في أحكامها", "callback_data": f"quiz:{number}"}],
            [{"text": "✍️ اختبرني في الآية", "callback_data": f"versequiz:{number}"}],
        ])

    def show_tafsirs(self, chat_id: int, number: int) -> None:
        keyboard = [[{
            "text": f"📖 {name}",
            "callback_data": f"tafsir:{number}:{tafsir_id}",
        }] for tafsir_id, name in TAFSIRS.items()]
        self.send(chat_id, "<b>اختر التفسير المطلوب:</b>", keyboard)

    def tafsir(self, chat_id: int, number: int, tafsir_id: str) -> None:
        if tafsir_id not in TAFSIRS:
            self.send(chat_id, "التفسير المطلوب غير متاح.")
            return
        ayah = self.quran.by_number(number)
        if not ayah:
            return
        self.action(chat_id, "typing")
        try:
            cache_key = (number, tafsir_id)
            with self.cache_lock:
                tafsir = self.tafsir_cache.get(cache_key)
            if tafsir is None:
                data = request_json(
                    f"{TAFSIR_API}/{tafsir_id}/surah/{ayah['surah']}/ayah/{ayah['ayah']}"
                )
                tafsir = data["ayah"]["text"]
                if not tafsir:
                    raise ValueError("نص التفسير غير متاح")
                with self.cache_lock:
                    self.tafsir_cache[cache_key] = tafsir
            # قد يكون تفسير الطبري طويلًا جدًا؛ نقسمه بدل بتره عند حد تيليجرام.
            chunks = [
                tafsir[index:index + 3000]
                for index in range(0, len(tafsir), 3000)
            ] or [""]
            for index, chunk in enumerate(chunks):
                heading = f"<b>📚 {TAFSIRS[tafsir_id]}:</b>\n\n" if index == 0 else ""
                source = (
                    "\n\n<i>المصدر: بيانات التفاسير عبر Al Furqan.</i>"
                    if index == len(chunks) - 1 else ""
                )
                self.send(chat_id, f"{heading}{html.escape(chunk)}{source}")
        except Exception:
            logging.exception("تعذر جلب التفسير")
            self.send(chat_id, "تعذر جلب التفسير الآن، حاول مرة أخرى لاحقًا.")

    def audio(self, chat_id: int, number: int, edition: str) -> None:
        if edition not in RECITERS:
            self.send(chat_id, "القارئ المطلوب غير متاح.")
            return
        self.action(chat_id, "upload_voice")
        try:
            cache_key = (number, edition)
            with self.cache_lock:
                audio_url = self.audio_cache.get(cache_key)
            if audio_url is None:
                data = request_json(f"{quran_api()}/ayah/{number}/{edition}")["data"]
                audio_url = data["audio"]
                with self.cache_lock:
                    self.audio_cache[cache_key] = audio_url
            self.api(
                "sendAudio",
                chat_id=chat_id,
                audio=audio_url,
                caption=f"تلاوة القارئ {RECITERS[edition]}",
            )
        except Exception:
            logging.exception("تعذر جلب الصوت")
            self.send(chat_id, "تعذر جلب التلاوة الآن، حاول مرة أخرى لاحقًا.")

    def quiz(self, chat_id: int, number: int) -> None:
        ayah = self.quran.by_number(number)
        if not ayah:
            return
        rules = analyse_tajweed(ayah["text"])
        if not rules:
            self.send(chat_id, "لا يوجد سؤال آلي مناسب لهذه الآية حاليًا.")
            return
        correct = rules[0].name
        options = [correct, "إقلاب", "إخفاء شفوي", "قلقلة"]
        options = list(dict.fromkeys(options))[:4]
        random.shuffle(options)
        keyboard = [[{
            "text": option,
            "callback_data": f"answer:{number}:{'1' if option == correct else '0'}",
        }] for option in options]
        self.send(
            chat_id,
            f"🧠 ما أحد الأحكام الموجودة في:\n\n<b>﴿ {html.escape(ayah['text'])} ﴾</b>",
            keyboard,
        )

    def verse_quiz(self, chat_id: int, number: int) -> None:
        ayah = self.quran.by_number(number)
        if not ayah:
            return
        words = ayah["text"].split()
        if len(words) < 2:
            self.send(chat_id, "هذه الآية قصيرة جدًا لإنشاء اختبار كلمات مناسب.")
            return
        missing_index = random.randrange(len(words))
        correct = words[missing_index]
        candidates = list(dict.fromkeys(
            [correct] + [word for word in words if word != correct]
        ))
        if len(candidates) < 4:
            nearby = [
                item["text"].split()[0]
                for item in self.quran.ayahs[max(0, number - 4):number + 3]
                if item["text"].split()
            ]
            candidates = list(dict.fromkeys(candidates + nearby))
        options = candidates[:4]
        if correct not in options:
            options[-1] = correct
        random.shuffle(options)
        shown_words = words.copy()
        shown_words[missing_index] = "_____"
        keyboard = [[{
            "text": option,
            "callback_data": (
                f"verseanswer:{number}:{missing_index}:"
                f"{'1' if option == correct else '0'}"
            ),
        }] for option in options]
        self.send(
            chat_id,
            "✍️ اختر الكلمة الناقصة:\n\n"
            f"<b>﴿ {html.escape(' '.join(shown_words))} ﴾</b>",
            keyboard,
        )

    def handle_callback(self, query: dict[str, Any]) -> None:
        self.api("answerCallbackQuery", callback_query_id=query["id"])
        chat_id = query["message"]["chat"]["id"]
        data = query.get("data", "")
        if data == "help":
            self.help(chat_id)
        elif data == "random":
            self.show_ayah(chat_id, random.choice(self.quran.ayahs))
        elif data == "reject":
            self.send(
                chat_id,
                "حسنًا 🌱 أرسل اسم السورة مع رقم الآية، أو اكتب جزءًا أطول "
                "من نص الآية وسأحاول مرة أخرى.",
            )
        elif data.startswith("candidate:"):
            ayah = self.quran.by_number(int(data.split(":")[1]))
            if ayah:
                self.confirm_ayah(chat_id, ayah)
        elif data.startswith("ayah:"):
            ayah = self.quran.by_number(int(data.split(":")[1]))
            if ayah:
                self.show_ayah(chat_id, ayah)
        elif data.startswith("tafsirs:"):
            self.show_tafsirs(chat_id, int(data.split(":")[1]))
        elif data.startswith("tafsir:"):
            _, number_text, tafsir_id = data.split(":", 2)
            self.action(chat_id, "typing")
            self.background(self.tafsir, chat_id, int(number_text), tafsir_id)
        elif data.startswith("audio:"):
            self.show_reciters(chat_id, int(data.split(":")[1]))
        elif data.startswith("play:"):
            _, number_text, edition = data.split(":", 2)
            if edition not in RECITERS:
                self.send(chat_id, "القارئ المطلوب غير متاح.")
                return
            self.preferred_reciter[chat_id] = edition
            if int(number_text):
                self.action(chat_id, "upload_voice")
                self.background(self.audio, chat_id, int(number_text), edition)
            else:
                self.send(
                    chat_id,
                    f"تم اختيار <b>{RECITERS[edition]}</b> قارئًا مفضّلًا ✅\n"
                    "عند فتح قائمة الاستماع سيظل بإمكانك اختيار قارئ آخر.",
                )
        elif data.startswith("quiz:"):
            self.quiz(chat_id, int(data.split(":")[1]))
        elif data.startswith("versequiz:"):
            self.verse_quiz(chat_id, int(data.split(":")[1]))
        elif data.startswith("verseanswer:"):
            _, number_text, index_text, result = data.split(":", 3)
            ayah = self.quran.by_number(int(number_text))
            words = ayah["text"].split() if ayah else []
            index = int(index_text)
            answer = words[index] if 0 <= index < len(words) else ""
            if result == "1":
                self.send(chat_id, "أحسنت، أكملت الآية بشكل صحيح ✅")
            else:
                self.send(
                    chat_id,
                    f"ليست الكلمة المقصودة. الإجابة الصحيحة: <b>{html.escape(answer)}</b> 🌱",
                )
        elif data.startswith("answer:"):
            correct = data.rsplit(":", 1)[1] == "1"
            self.send(chat_id, "أحسنت، إجابة صحيحة ✅" if correct else "ليست الإجابة المقصودة، حاول مجددًا 🌱")

    def handle_message(self, message: dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        if text in {"/start", "/start@tajweedbot"}:
            self.welcome(chat_id)
        elif text == "/help":
            self.help(chat_id)
        elif text == "/random":
            self.show_ayah(chat_id, random.choice(self.quran.ayahs))
        elif text == "/readers":
            self.show_reciters(chat_id)
        elif text.startswith("/"):
            self.send(chat_id, "الأمر غير معروف. استخدم /help.")
        else:
            normalized_digits = western_digits(text)
            reference = re.fullmatch(
                r"\s*(\d{1,3})\s*[:/،-]\s*(\d{1,3})\s*",
                normalized_digits,
            )
            if reference:
                surah, verse = map(int, reference.groups())
                match = next(
                    (a for a in self.quran.ayahs if a["surah"] == surah and a["ayah"] == verse),
                    None,
                )
                self.show_matches(chat_id, [match] if match else [])
            else:
                named_reference = parse_surah_reference(text)
                if named_reference:
                    surah, verse = named_reference
                    match = next(
                        (
                            ayah for ayah in self.quran.ayahs
                            if ayah["surah"] == surah and ayah["ayah"] == verse
                        ),
                        None,
                    )
                    self.show_matches(chat_id, [match] if match else [])
                else:
                    self.show_matches(chat_id, self.quran.find(text))

    def run(self) -> None:
        logging.info("البوت يعمل الآن")
        while True:
            try:
                updates = self.api(
                    "getUpdates",
                    offset=self.offset,
                    timeout=30,
                    allowed_updates=["message", "callback_query"],
                )
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if "message" in update:
                        self.dispatch(self.handle_message, update["message"])
                    elif "callback_query" in update:
                        self.dispatch(self.handle_callback, update["callback_query"])
            except (requests.RequestException, TimeoutError):
                logging.warning("مشكلة اتصال؛ إعادة المحاولة بعد 3 ثوان")
                time.sleep(3)
            except Exception:
                logging.exception("خطأ غير متوقع")
                time.sleep(2)


def main() -> None:
    load_env()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "ضع التوكن الجديد في ملف .env باسم TELEGRAM_BOT_TOKEN "
            "(لا تستخدم التوكن الذي نُشر في المحادثة)."
        )
    quran = QuranStore()
    quran.load()
    Bot(token, quran).run()


if __name__ == "__main__":
    main()
