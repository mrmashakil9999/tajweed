import unittest

from main import (
    Bot,
    QuranStore,
    RECITERS,
    TAFSIRS,
    parse_surah_reference,
    western_digits,
)
from tajweed import analyse_tajweed, normalize_arabic


class TajweedTests(unittest.TestCase):
    def names(self, text):
        return {rule.name for rule in analyse_tajweed(text)}

    def test_normalization(self):
        self.assertEqual(normalize_arabic("مِن شَرِّ"), "من شر")

    def test_dagger_alif_can_expand_to_normal_spelling(self):
        self.assertEqual(
            normalize_arabic("أَعْطَيْنَٰكَ", expand_dagger_alif=True),
            "اعطيناك",
        )

    def test_kawthar_common_spelling_is_found(self):
        store = QuranStore()
        store.ayahs = [{
            "number": 6205,
            "surah": 108,
            "ayah": 1,
            "text": "إِنَّآ أَعْطَيْنَٰكَ ٱلْكَوْثَرَ",
        }]
        for item in store.ayahs:
            item["_search"] = normalize_arabic(item["text"])
            item["_search_expanded"] = normalize_arabic(
                item["text"], expand_dagger_alif=True
            )
        self.assertEqual(store.find("انا اعطيناك الكوثر")[0]["surah"], 108)

    def test_ikhfa(self):
        self.assertIn("إخفاء حقيقي", self.names("مِنْ شَرِّ"))

    def test_iqlab(self):
        self.assertIn("إقلاب", self.names("مِنْ بَعْدِ"))

    def test_meem(self):
        self.assertIn("إخفاء شفوي", self.names("عَلَيْهِمْ بِمُصَيْطِرٍ"))

    def test_stop_qalqalah(self):
        self.assertIn("قلقلة عند الوقف", self.names("خَلَقَ"))


class ReciterTests(unittest.TestCase):
    def test_callback_data_fits_telegram_limit(self):
        for edition in RECITERS:
            self.assertLessEqual(len(f"play:6236:{edition}".encode()), 64)

    def test_reciter_keyboard_has_every_reciter(self):
        bot = object.__new__(Bot)
        buttons = [button for row in bot.reciters_keyboard(262) for button in row]
        self.assertEqual(len(buttons), len(RECITERS))
        self.assertTrue(all(button["callback_data"].startswith("play:262:") for button in buttons))

    def test_bot_has_separate_caches(self):
        bot = object.__new__(Bot)
        bot.tafsir_cache = {}
        bot.audio_cache = {}
        bot.tafsir_cache[(262, "muyassar")] = "تفسير"
        bot.audio_cache[(262, "ar.alafasy")] = "audio"
        self.assertEqual(bot.tafsir_cache[(262, "muyassar")], "تفسير")
        self.assertEqual(bot.audio_cache[(262, "ar.alafasy")], "audio")

    def test_muhammad_ayyoub_is_available(self):
        self.assertEqual(RECITERS["ar.muhammadayyoub"], "محمد أيوب")

    def test_requested_tafsirs_are_available(self):
        self.assertEqual(
            set(TAFSIRS),
            {"muyassar", "al-saddi", "al-tabari"},
        )


class FlexibleSearchTests(unittest.TestCase):
    def test_arabic_digits_are_supported(self):
        self.assertEqual(western_digits("٢:٢٥٥"), "2:255")

    def test_surah_name_and_ayah_number(self):
        self.assertEqual(parse_surah_reference("سورة البقرة آية 255"), (2, 255))

    def test_misspelled_surah_name(self):
        self.assertEqual(parse_surah_reference("البقره ٢٥٥"), (2, 255))

    def test_misspelled_ayah_text_returns_candidate(self):
        store = QuranStore()
        store.ayahs = [{
            "number": 1,
            "surah": 1,
            "ayah": 1,
            "text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
            "_search": normalize_arabic("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"),
            "_search_expanded": normalize_arabic(
                "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                expand_dagger_alif=True,
            ),
        }]
        self.assertEqual(store.find("بسم اللة الرحمن الرحيم")[0]["number"], 1)


if __name__ == "__main__":
    unittest.main()
