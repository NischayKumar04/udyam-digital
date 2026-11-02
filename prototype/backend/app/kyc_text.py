"""KYC results in the owner's language.

The data shows Tamil, Kannada and Punjabi speakers dropping out at this step, so the
reasons must be readable in their language. Any check without a translation here stays
in English rather than being machine-translated, because these messages can contain
personal details that shouldn't go to an AI provider.
"""
from .kyc_checks import Check, KycResult

DOCUMENT_NAMES = {
    "Hindi": {"gst": "GST प्रमाणपत्र", "udyam": "उद्यम प्रमाणपत्र", "signatory_id": "हस्ताक्षरकर्ता का पहचान पत्र", "address_proof": "पते का प्रमाण"},
    "Tamil": {"gst": "GST சான்றிதழ்", "udyam": "உத்யம் சான்றிதழ்", "signatory_id": "கையொப்பமிடுபவரின் அடையாள அட்டை", "address_proof": "முகவரிச் சான்று"},
    "Kannada": {"gst": "GST ಪ್ರಮಾಣಪತ್ರ", "udyam": "ಉದ್ಯಮ್ ಪ್ರಮಾಣಪತ್ರ", "signatory_id": "ಸಹಿ ಮಾಡುವವರ ಗುರುತಿನ ಚೀಟಿ", "address_proof": "ವಿಳಾಸದ ಪುರಾವೆ"},
}

MESSAGES = {
    "Hindi": {
        "DOCUMENT_UNREADABLE": "आपका {document} धुंधला है और पढ़ा नहीं जा रहा। कृपया साफ़ फ़ोटो लीजिए।",
        "WRONG_DOCUMENT": "यह {document} नहीं लगता। कृपया सही दस्तावेज़ अपलोड कीजिए।",
        "GST_FROM_REGISTRY": "GST प्रमाणपत्र की ज़रूरत नहीं। हमने आपका GSTIN रजिस्ट्री से जाँच लिया है।",
        "GST_NOT_NEEDED": "आपके प्लान में GST पंजीकरण ज़रूरी नहीं है, इसलिए हम यह नहीं माँगेंगे।",
        "DOCUMENT_MISSING": "कृपया अपना {document} अपलोड कीजिए।",
        "UDYAM_FROM_REGISTRY": "उद्यम प्रमाणपत्र अपलोड नहीं हुआ था, इसलिए हमने आपके नंबर से इसे रजिस्ट्री से ले लिया।",
        "UDYAM_NOT_PROVIDED": "उद्यम पंजीकरण नहीं दिया गया। आप इसके बिना भी आगे बढ़ सकते हैं।",
        "ADDRESS_FROM_GST": "पते के प्रमाण की ज़रूरत नहीं। इंस्टॉलेशन आपके GST वाले पते पर है।",
        "GSTIN_INACTIVE": "यह GSTIN रजिस्ट्री में {status} है। जिन सेवाओं के लिए GST ज़रूरी है, वे इस पर नहीं मिल सकतीं।",
        "GSTIN_INVALID": "इस प्रमाणपत्र का GSTIN सही नहीं है। हमारी टीम इसकी जाँच करेगी।",
        "GSTIN_DIFFERS_FROM_APPLICATION": "इस प्रमाणपत्र का GSTIN आपके आवेदन वाले GSTIN से अलग है।",
        "LEGAL_NAME_MISMATCH": "इस प्रमाणपत्र का कानूनी नाम रजिस्ट्री से मेल नहीं खाता। रजिस्ट्री में लिखा है: {expected}।",
        "UDYAM_NUMBER_BLANK": "इस उद्यम प्रमाणपत्र पर पंजीकरण संख्या खाली है। कृपया पूरी कॉपी अपलोड कीजिए।",
        "ADDRESS_PROOF_STALE": "यह बिल {age} दिन पुराना है। हमें पिछले {limit} दिनों का बिल चाहिए।",
        "BILL_ADDRESS_MISMATCH": "इस बिल का पता आपके GST वाले पते से मेल नहीं खाता।",
        "ID_EXPIRED": "यह पहचान पत्र {date} को समाप्त हो चुका है। कृपया मान्य पहचान पत्र अपलोड कीजिए।",
        "SIGNATORY_NOT_APPLICANT": "पहचान पत्र {name} के नाम पर है, पर आवेदन {applicant} ने किया है। हमें पुष्टि करनी होगी कि हस्ताक्षर कौन कर सकता है।",
        "SIGNATORY_ROLE_UNUSUAL": "पहचान पत्र पर पद \"{role}\" लिखा है। हम ई-साइन के समय इसकी पुष्टि करेंगे।",
    },
    "Tamil": {
        "DOCUMENT_UNREADABLE": "உங்கள் {document} மங்கலாக உள்ளது, படிக்க முடியவில்லை. தெளிவான படம் எடுத்து அனுப்புங்கள்.",
        "WRONG_DOCUMENT": "இது {document} போலத் தெரியவில்லை. சரியான ஆவணத்தைப் பதிவேற்றுங்கள்.",
        "GST_FROM_REGISTRY": "GST சான்றிதழ் தேவையில்லை. உங்கள் GSTIN-ஐ பதிவேட்டில் சரிபார்த்துவிட்டோம்.",
        "GST_NOT_NEEDED": "உங்கள் திட்டத்திற்கு GST பதிவு தேவையில்லை, அதனால் அதைக் கேட்க மாட்டோம்.",
        "DOCUMENT_MISSING": "உங்கள் {document} பதிவேற்றுங்கள்.",
        "UDYAM_FROM_REGISTRY": "உத்யம் சான்றிதழ் பதிவேற்றப்படவில்லை, அதனால் உங்கள் எண்ணைக் கொண்டு பதிவேட்டிலிருந்து பெற்றுக்கொண்டோம்.",
        "UDYAM_NOT_PROVIDED": "உத்யம் பதிவு வழங்கப்படவில்லை. அது இல்லாமலும் தொடரலாம்.",
        "ADDRESS_FROM_GST": "முகவரிச் சான்று தேவையில்லை. நிறுவல் உங்கள் GST முகவரியில் நடக்கும்.",
        "GSTIN_INACTIVE": "இந்த GSTIN பதிவேட்டில் {status} என உள்ளது. GST தேவைப்படும் சேவைகளை இதில் வழங்க முடியாது.",
        "GSTIN_INVALID": "இந்தச் சான்றிதழில் உள்ள GSTIN சரியாக இல்லை. எங்கள் குழு இதைச் சரிபார்க்கும்.",
        "GSTIN_DIFFERS_FROM_APPLICATION": "இந்தச் சான்றிதழில் உள்ள GSTIN உங்கள் விண்ணப்பத்தில் உள்ளதிலிருந்து வேறுபடுகிறது.",
        "LEGAL_NAME_MISMATCH": "இந்தச் சான்றிதழில் உள்ள சட்டப் பெயர் பதிவேட்டுடன் பொருந்தவில்லை. பதிவேட்டில் இருப்பது: {expected}.",
        "UDYAM_NUMBER_BLANK": "இந்த உத்யம் சான்றிதழில் பதிவு எண் காலியாக உள்ளது. முழுமையான நகலைப் பதிவேற்றுங்கள்.",
        "ADDRESS_PROOF_STALE": "இந்த பில் {age} நாட்கள் பழையது. கடந்த {limit} நாட்களுக்குள் உள்ள பில் தேவை.",
        "BILL_ADDRESS_MISMATCH": "இந்த பில்லில் உள்ள முகவரி உங்கள் GST முகவரியுடன் பொருந்தவில்லை.",
        "ID_EXPIRED": "இந்த அடையாள அட்டை {date} அன்று காலாவதியானது. செல்லுபடியாகும் அட்டையைப் பதிவேற்றுங்கள்.",
        "SIGNATORY_NOT_APPLICANT": "அடையாள அட்டை {name} பெயரில் உள்ளது, ஆனால் விண்ணப்பித்தவர் {applicant}. யார் கையொப்பமிடலாம் என்பதை உறுதி செய்ய வேண்டும்.",
        "SIGNATORY_ROLE_UNUSUAL": "அடையாள அட்டையில் பதவி \"{role}\" என உள்ளது. மின்-கையொப்பத்தின்போது இதை உறுதி செய்வோம்.",
    },
    "Kannada": {
        "DOCUMENT_UNREADABLE": "ನಿಮ್ಮ {document} ಮಸುಕಾಗಿದೆ, ಓದಲು ಆಗುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟವಾದ ಫೋಟೋ ತೆಗೆಯಿರಿ.",
        "WRONG_DOCUMENT": "ಇದು {document} ಎಂದು ಕಾಣುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಸರಿಯಾದ ದಾಖಲೆಯನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.",
        "GST_FROM_REGISTRY": "GST ಪ್ರಮಾಣಪತ್ರ ಬೇಕಿಲ್ಲ. ನಿಮ್ಮ GSTIN ಅನ್ನು ನೋಂದಣಿಯಲ್ಲಿ ಪರಿಶೀಲಿಸಿದ್ದೇವೆ.",
        "GST_NOT_NEEDED": "ನಿಮ್ಮ ಯೋಜನೆಗೆ GST ನೋಂದಣಿ ಬೇಕಿಲ್ಲ, ಆದ್ದರಿಂದ ಅದನ್ನು ಕೇಳುವುದಿಲ್ಲ.",
        "DOCUMENT_MISSING": "ದಯವಿಟ್ಟು ನಿಮ್ಮ {document} ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.",
        "UDYAM_FROM_REGISTRY": "ಉದ್ಯಮ್ ಪ್ರಮಾಣಪತ್ರ ಅಪ್‌ಲೋಡ್ ಆಗಿರಲಿಲ್ಲ, ಆದ್ದರಿಂದ ನಿಮ್ಮ ಸಂಖ್ಯೆಯಿಂದ ನೋಂದಣಿಯಿಂದ ಪಡೆದಿದ್ದೇವೆ.",
        "UDYAM_NOT_PROVIDED": "ಉದ್ಯಮ್ ನೋಂದಣಿ ನೀಡಿಲ್ಲ. ಅದಿಲ್ಲದೆಯೂ ಮುಂದುವರಿಯಬಹುದು.",
        "ADDRESS_FROM_GST": "ವಿಳಾಸದ ಪುರಾವೆ ಬೇಕಿಲ್ಲ. ಅಳವಡಿಕೆ ನಿಮ್ಮ GST ವಿಳಾಸದಲ್ಲಿ ಆಗುತ್ತದೆ.",
        "GSTIN_INACTIVE": "ಈ GSTIN ನೋಂದಣಿಯಲ್ಲಿ {status} ಎಂದಿದೆ. GST ಅಗತ್ಯವಿರುವ ಸೇವೆಗಳನ್ನು ಇದರ ಮೇಲೆ ನೀಡಲಾಗದು.",
        "GSTIN_INVALID": "ಈ ಪ್ರಮಾಣಪತ್ರದಲ್ಲಿರುವ GSTIN ಸರಿಯಾಗಿಲ್ಲ. ನಮ್ಮ ತಂಡ ಇದನ್ನು ಪರಿಶೀಲಿಸುತ್ತದೆ.",
        "GSTIN_DIFFERS_FROM_APPLICATION": "ಈ ಪ್ರಮಾಣಪತ್ರದಲ್ಲಿರುವ GSTIN ನಿಮ್ಮ ಅರ್ಜಿಯಲ್ಲಿರುವುದಕ್ಕಿಂತ ಬೇರೆಯಾಗಿದೆ.",
        "LEGAL_NAME_MISMATCH": "ಈ ಪ್ರಮಾಣಪತ್ರದ ಕಾನೂನು ಹೆಸರು ನೋಂದಣಿಗೆ ಹೊಂದುತ್ತಿಲ್ಲ. ನೋಂದಣಿಯಲ್ಲಿರುವುದು: {expected}.",
        "UDYAM_NUMBER_BLANK": "ಈ ಉದ್ಯಮ್ ಪ್ರಮಾಣಪತ್ರದಲ್ಲಿ ನೋಂದಣಿ ಸಂಖ್ಯೆ ಖಾಲಿ ಇದೆ. ದಯವಿಟ್ಟು ಪೂರ್ಣ ಪ್ರತಿಯನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.",
        "ADDRESS_PROOF_STALE": "ಈ ಬಿಲ್ {age} ದಿನಗಳಷ್ಟು ಹಳೆಯದು. ಕಳೆದ {limit} ದಿನಗಳ ಬಿಲ್ ಬೇಕು.",
        "BILL_ADDRESS_MISMATCH": "ಈ ಬಿಲ್‌ನ ವಿಳಾಸ ನಿಮ್ಮ GST ವಿಳಾಸಕ್ಕೆ ಹೊಂದುತ್ತಿಲ್ಲ.",
        "ID_EXPIRED": "ಈ ಗುರುತಿನ ಚೀಟಿ {date} ರಂದು ಅವಧಿ ಮುಗಿದಿದೆ. ಮಾನ್ಯವಾದ ಚೀಟಿಯನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.",
        "SIGNATORY_NOT_APPLICANT": "ಗುರುತಿನ ಚೀಟಿ {name} ಹೆಸರಿನಲ್ಲಿದೆ, ಆದರೆ ಅರ್ಜಿ ಹಾಕಿದವರು {applicant}. ಸಹಿ ಮಾಡುವ ಅಧಿಕಾರ ಯಾರಿಗಿದೆ ಎಂದು ಖಚಿತಪಡಿಸಬೇಕು.",
        "SIGNATORY_ROLE_UNUSUAL": "ಗುರುತಿನ ಚೀಟಿಯಲ್ಲಿ ಹುದ್ದೆ \"{role}\" ಎಂದಿದೆ. ಇ-ಸಹಿ ಸಮಯದಲ್ಲಿ ಇದನ್ನು ಖಚಿತಪಡಿಸುತ್ತೇವೆ.",
    },
}


def _localize_check(check: Check, language: str) -> Check:
    template = MESSAGES.get(language, {}).get(check.code)
    if template is None:
        return check
    document = DOCUMENT_NAMES[language].get(check.document or "", "")
    return check.model_copy(update={"message": template.format(document=document, **check.params)})


def localize(result: KycResult, language: str) -> KycResult:
    return result.model_copy(update={"checks": [_localize_check(check, language) for check in result.checks]})
