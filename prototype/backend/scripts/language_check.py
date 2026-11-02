"""Checks that the advisor really replies in each chat language, on the real AI models.

Uses free-tier quota, so it paces itself. Run from prototype/backend:
    python -m scripts.language_check
"""
import logging
import sys
import time
import unicodedata

from app.advisor import send_message, start_session

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.WARNING, format="  LLM: %(message)s", stream=sys.stdout)
logging.getLogger("httpx").setLevel(logging.ERROR)

PAUSE_SECONDS = 15

# Each message: a salon in a city, 3 staff, one site, no GST, wants CCTV.
CASES = {
    "Marathi": ("DEVANAGARI", "माझे पुण्यात सलून आहे, 3 लोक काम करतात, एकच दुकान, GST नाही. मला CCTV हवा आहे."),
    "Telugu": ("TELUGU", "నాకు హైదరాబాద్‌లో సెలూన్ ఉంది, 3 మంది పని చేస్తారు, ఒకే షాపు, GST లేదు. నాకు CCTV కావాలి."),
    "Malayalam": ("MALAYALAM", "എനിക്ക് കൊച്ചിയിൽ ഒരു സലൂൺ ഉണ്ട്, 3 പേർ ജോലി ചെയ്യുന്നു, ഒരു കട മാത്രം, GST ഇല്ല. എനിക്ക് CCTV വേണം."),
    "Bengali": ("BENGALI", "কলকাতায় আমার একটি সেলুন আছে, ৩ জন কাজ করেন, একটাই দোকান, GST নেই। আমার CCTV চাই।"),
    "Gujarati": ("GUJARATI", "અમદાવાદમાં મારું સલૂન છે, 3 લોકો કામ કરે છે, એક જ દુકાન, GST નથી. મને CCTV જોઈએ છે."),
    "Punjabi": ("GURMUKHI", "ਲੁਧਿਆਣੇ ਵਿੱਚ ਮੇਰਾ ਸੈਲੂਨ ਹੈ, 3 ਲੋਕ ਕੰਮ ਕਰਦੇ ਹਨ, ਇੱਕੋ ਦੁਕਾਨ, GST ਨਹੀਂ ਹੈ। ਮੈਨੂੰ CCTV ਚਾਹੀਦਾ ਹੈ।"),
}


def script_share(text: str, script: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    return sum(script in unicodedata.name(ch, "") for ch in letters) / max(1, len(letters))


passed = 0
for language, (script, message) in CASES.items():
    started = start_session(language)
    time.sleep(3)
    result = send_message(started.session_id, message)
    recommendation = result.recommendation
    bundle = {item.product_id for item in recommendation.bundle} if recommendation else set()
    greeting_share = script_share(started.reply, script)
    reply_share = script_share(result.reply, script)
    ok = result.mode == "ai" and {"P01", "P07", "P23"} <= bundle and reply_share >= 0.5 and greeting_share >= 0.5
    passed += ok
    print(f"{'PASS' if ok else 'FAIL'}  {language}: mode={result.mode} bundle={sorted(bundle)} greeting in script {greeting_share:.0%}, reply in script {reply_share:.0%}")
    print("   ", result.reply[:170].replace("\n", " "))
    time.sleep(PAUSE_SECONDS)
print(f"\n{passed}/{len(CASES)} languages passed")
