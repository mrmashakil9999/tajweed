"""قواعد أولية قابلة للاختبار لاكتشاف أشهر أحكام التجويد في نص مشكول."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


HARAKAT = "\u064b-\u065f\u0670\u06d6-\u06ed"
TANWEEN = {"ً", "ٌ", "ٍ"}
IZHAR = set("ءهعحغخ")
IDGHAM_GHUNNAH = set("ينمو")
IDGHAM_NO_GHUNNAH = set("رل")
IQLAB = {"ب"}
IKHFA = set("تثجدذزسشصضطظفقك")
QALQALAH = set("قطبجد")


@dataclass(frozen=True)
class TajweedRule:
    name: str
    explanation: str


def normalize_arabic(text: str, expand_dagger_alif: bool = False) -> str:
    # في الرسم العثماني تُكتب ألف بعض الكلمات ألفًا خنجرية مثل
    # ﴿أَعْطَيْنَٰكَ﴾، بينما يكتبها المستخدم «أعطيناك».
    if expand_dagger_alif:
        text = text.replace("\u0670", "ا")
    text = re.sub(f"[{HARAKAT}]", "", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}))
    text = re.sub(r"[^\u0621-\u063a\u0641-\u064a ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _letters(text: str) -> list[tuple[str, str]]:
    """يعيد الحرف مع حركاته، متجاهلًا علامات المصحف."""
    result: list[tuple[str, str]] = []
    for char in text:
        if "\u0621" <= char <= "\u064a" or char in "ٱ":
            result.append((char, ""))
        elif result and (unicodedata.combining(char) or char == "ٰ"):
            letter, marks = result[-1]
            result[-1] = (letter, marks + char)
    return result


def analyse_tajweed(text: str) -> list[TajweedRule]:
    letters = _letters(text)
    found: list[TajweedRule] = []

    def add(name: str, explanation: str) -> None:
        rule = TajweedRule(name, explanation)
        if rule not in found:
            found.append(rule)

    for index, (letter, marks) in enumerate(letters[:-1]):
        nxt, _ = letters[index + 1]
        is_noon_sakin = letter == "ن" and "ْ" in marks
        has_tanween = any(mark in marks for mark in TANWEEN)
        if is_noon_sakin or has_tanween:
            subject = "النون الساكنة" if is_noon_sakin else "التنوين"
            if nxt in IZHAR:
                add("إظهار حلقي", f"{subject} قبل حرف {nxt}.")
            elif nxt in IDGHAM_GHUNNAH:
                add("إدغام بغنة", f"{subject} قبل حرف {nxt}، عند الوصل بين كلمتين.")
            elif nxt in IDGHAM_NO_GHUNNAH:
                add("إدغام بغير غنة", f"{subject} قبل حرف {nxt}، عند الوصل بين كلمتين.")
            elif nxt in IQLAB:
                add("إقلاب", f"{subject} قبل الباء؛ يُقلب إلى ميم مخفاة مع الغنة.")
            elif nxt in IKHFA:
                add("إخفاء حقيقي", f"{subject} قبل حرف {nxt}.")

        if letter == "م" and "ْ" in marks:
            if nxt == "ب":
                add("إخفاء شفوي", "ميم ساكنة قبل الباء مع الغنة.")
            elif nxt == "م":
                add("إدغام شفوي", "ميم ساكنة قبل الميم مع الغنة.")
            else:
                add("إظهار شفوي", f"ميم ساكنة قبل حرف {nxt}.")

        if letter in QALQALAH and "ْ" in marks:
            add("قلقلة صغرى", f"حرف {letter} ساكن في أثناء القراءة.")

        if letter in {"ا", "و", "ي", "ى"}:
            previous_marks = letters[index - 1][1] if index else ""
            natural = (
                letter in {"ا", "ى"} and "َ" in previous_marks
                or letter == "و" and "ُ" in previous_marks and "ْ" in marks
                or letter == "ي" and "ِ" in previous_marks and "ْ" in marks
            )
            if natural:
                add("مد طبيعي", f"موضع مد عند حرف {letter} بمقدار حركتين غالبًا.")

    if letters:
        final_letter, _ = letters[-1]
        if final_letter in QALQALAH:
            add("قلقلة عند الوقف", f"عند الوقف على حرف {final_letter} الساكن عارضًا.")
        if final_letter in {"ة", "ه"}:
            add("الوقف", "يُراعى الوقف بالسكون، والتاء المربوطة تُوقف هاءً.")

    return found
