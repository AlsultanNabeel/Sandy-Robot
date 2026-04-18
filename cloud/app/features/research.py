import json
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

# دالة تحدد نوع البحث قب البحث
def detect_research_type(message: str) -> str:
    text = (message or "").strip().lower()

    education_triggers = [
        "جامعة", "جامعات", "ماجستير", "ماجيستير", "ماستر", "بكالوريوس", "دكتوراه",
        "منحة", "قبول", "تقديم", "admission", "university", "universidad",
        "master", "masters", "phd", "bachelor", "degree",
        "ielts", "toefl",
        "روبوت", "روبوتكس", "robotics", "automation", "automatica", "robótica", "robotica"
    ]

    travel_triggers = [
        "سافر", "سفر", "فندق", "رحلة", "تأشيرة", "فيزا", "hotel", "trip", "travel", "visa"
    ]

    product_triggers = [
        "اشتري", "اشتريلي", "منتج", "منتجات", "سعر", "مقارنة أسعار",
        "buy", "price", "product", "products", "compare"
    ]

    news_triggers = [
        "خبر", "أخبار", "اليوم", "آخر", "اخر", "latest", "news", "update", "updates"
    ]

    if any(word in text for word in education_triggers):
        return "education"

    if any(word in text for word in travel_triggers):
        return "travel"

    if any(word in text for word in product_triggers):
        return "product"

    if any(word in text for word in news_triggers):
        return "news"

    return "general"



# هاي الدالة بتحاول تفهم من كلام المستخدم كم نتيجة بده بالزبط، وإذا ما حدد عدد بترجع رقم افتراضي.
def extract_requested_result_count(message: str, default: int = 5) -> int:
    text = (message or "").strip().lower()

    arabic_number_words = {
        "واحد": 1,
        "وحدة": 1,
        "واحدة": 1,
        "اثنين": 2,
        "اتنين": 2,
        "اثنتين": 2,
        "ثلاثة": 3,
        "ثلاث": 3,
        "اربعة": 4,
        "اربع": 4,
        "أربع": 4,
        "أربعة": 4,
        "خمسة": 5,
        "ستة": 6,
        "سبعة": 7,
        "ثمانية": 8,
        "تسعة": 9,
        "عشرة": 10,
    }

    # أولاً: لو فيه رقم مكتوب مباشرة
    match = re.search(r"\b(\d+)\b", text)
    if match:
        try:
            value = int(match.group(1))
            return max(1, min(value, 20))
        except Exception:
            pass

    # ثانياً: لو العدد مكتوب كلمات
    for word, value in arabic_number_words.items():
        if word in text:
            return value

    # ثالثاً: لو الطلب بصيغة مفردة واضحة
    single_result_triggers = [
        "أفضل جامعة",
        "افضل جامعة",
        "أرخص جامعة",
        "ارخص جامعة",
        "جامعة وحدة",
        "جامعة واحدة",
        "صفحة وحدة",
        "صفحة واحدة",
        "أفضل صفحة",
        "افضل صفحة",
        "أرخص صفحة",
        "ارخص صفحة",
        "best university",
        "cheapest university",
        "one university",
        "single university",
        "one page",
        "single page",
        "best page",
        "cheapest page",
    ]

    lowered = text.lower()
    if any(trigger.lower() in lowered for trigger in single_result_triggers):
        return 1

    return default



# هاي الدالة بتحاول تفهم شو نوع الفلترة أو المقارنة اللي بدها ياها من كلام المستخدم.
def detect_research_preference(message: str) -> Dict[str, Any]:
    text = str(message or "").strip().lower()

    return {
        "best_only": any(x in text for x in [
            "أفضل", "افضل", "best", "top", "الأقوى", "الاقوى"
        ]),
        "cheapest_only": any(x in text for x in [
            "أرخص", "ارخص", "cheapest", "lowest price", "lowest tuition"
        ]),
        "no_ielts": any(x in text for x in [
            "بدون ielts", "ما يطلب ielts", "بدون توفل", "ما يطلب توفل",
            "بدون toefl", "no ielts", "no toefl"
        ]),
        "english_only": any(x in text for x in [
            "بالانجليزي", "بالإنجليزي", "باللغة الإنجليزية",
            "english", "english only", "in english"
        ]),
        "official_only": any(x in text for x in [
            "رسمي", "رسمية", "official", "official only"
        ]),
    }



# بتشيك إذا الرسالة فيها طلب بحث أو مقارنة جامعات أو منح
def is_research_request(message: str) -> bool:
    text = (message or "").strip().lower()

    triggers = [
        "ابحث", "ابحثي", "دوري", "دورلي", "research", "find",
        "جامعة", "جامعات", "ماجستير", "masters", "robotics",
        "قارن", "قارنة", "منحة", "قبول", "admission", "ielts", "toefl"
    ]

    return any(t in text for t in triggers)





# هاي الدالة بتعرف إذا المستخدم عم يبني على نتائج البحث السابقة بدل ما يبدأ بحث جديد من الصفر.
def is_research_followup_request(message: str) -> bool:
    text = str(message or "").strip().lower()

    triggers = [
        "من هدول", "من بينهم", "من النتائج", "فيهم", "منهم",
        "which of these", "from these", "among them", "among these"
    ]

    return any(t in text for t in triggers)





# هاي الدالة بتنظف الرابط بشكل بسيط حتى نقدر نكتشف إذا نفس الصفحة مكررة بنسخة لغة ثانية أو بصيغة مختلفة.
def normalize_result_url(url: str) -> str:
    url = str(url or "").strip().lower()
    url = url.rstrip("/")

    replacements = [
        "/en",
        "/es",
        "/ar",
        "/fr",
        "/de",
        "/ca",
        "/eu"
    ]

    for suffix in replacements:
        if url.endswith(suffix):
            url = url[: -len(suffix)]

    # شيل query params إذا موجودة
    url = url.split("?")[0]

    return url



# هاي الدالة بتنظف اسم البرنامج عشان نقدر نكشف التكرار حتى لو الاسم طالع بلغة ثانية أو بصياغة مختلفة شوي.
def normalize_program_name(name: str) -> str:
    name = str(name or "").strip().lower()

    replacements = {
        "robótica": "robotics",
        "robotica": "robotics",
        "automatización": "automation",
        "automatizacion": "automation",
        "automática": "automation",
        "automatica": "automation",
        "máster": "master",
        "master's": "master",
        "masters": "master",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# هاي الدالة بتبني مفتاح تقريبي للنتيجة حتى نعرف إذا نفس الجامعة/البرنامج طالع أكثر من مرة.
def build_result_dedup_key(item: Dict[str, Any]) -> str:
    page_data = item.get("page_data", {}) or {}

    institution = str(page_data.get("institution_name") or "").strip().lower()
    program = normalize_program_name(page_data.get("program_name") or item.get("source_title") or "")
    source_url = normalize_result_url(item.get("source_url") or "")
    source_domain = ""

    try:
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        source_domain = parsed.netloc.replace("www.", "").strip().lower()
        source_path = parsed.path.strip().lower()
    except Exception:
        source_domain = ""
        source_path = ""

    if institution and program:
        return f"{institution}::{program}"

    if source_domain and program:
        return f"{source_domain}::{program}"

    if source_domain and source_path:
        return f"{source_domain}::{source_path}"

    if source_url:
        return source_url

    return normalize_program_name(item.get("source_title") or "")


# هاي الدالة بتشيل النتائج المكررة، مثل نفس الجامعة أو نفس البرنامج إذا طلع بأكثر من رابط أو لغة.
def deduplicate_research_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique_results = []
    seen_keys = set()

    for item in results:
        key = build_result_dedup_key(item)
        if not key:
            continue

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_results.append(item)

    return unique_results




# بيلخص نتائج البحث الجامعي بشكل بسيط للمستخدم
def summarize_research_results(results: List[Dict[str, Any]], requested_count: int = 5) -> str:
    def localize_display_value(value: Any, field_type: str = "") -> str:
        if isinstance(value, dict):
            if field_type == "deadline":
                parts = []
                for k, v in value.items():
                    key = str(k).replace("_", " ").strip()
                    val = str(v).strip()
                    if val:
                        parts.append(f"{key}: {val}")
                return " | ".join(parts) if parts else "غير مذكور بوضوح"
            value = str(value)

        if isinstance(value, list):
            value = " | ".join(str(x).strip() for x in value if str(x).strip())

        value = str(value or "").strip()
        lowered = value.lower()
        # إذا القيمة جاية كنص على شكل dict مثل "{'phase_0': '...'}"
        if field_type == "deadline" and value.startswith("{") and value.endswith("}"):
            try:
                parsed = json.loads(value.replace("'", '"'))
                if isinstance(parsed, dict):
                    parts = []
                    for k, v in parsed.items():
                        key = str(k).replace("_", " ").strip()
                        val = str(v).strip()
                        if val:
                            parts.append(f"{key}: {val}")
                    return " | ".join(parts) if parts else "غير مذكور بوضوح"
            except Exception:
                pass

        unknown_values = {
            "unknown",
            "not specified",
            "not specified.",
            "not specified in the provided text",
            "not specified in the provided text.",
            "n/a",
            "none",
            "no especificado",
            "no especificado en la página",
            "no especificado en la página.",
            "no especificado en la pagina",
            "no especificado en la pagina.",
            "desconocido"
        }

        if lowered in unknown_values:
            if field_type == "tuition":
                return "غير مذكورة بوضوح"
            if field_type == "deadline":
                return "غير مذكور بوضوح"
            return "غير واضح"

        if lowered in {"yes", "true", "required"}:
            return "نعم"

        if lowered in {"no", "false", "not required"}:
            return "لا"

        return value

    if not results:
        return "[think] ما لقيت نتائج واضحة من البحث حالياً."

    lines = ["[think] رتبت لك النتائج بشكل أوضح، وحاولت أعتمد على المصادر الرسمية قدر الإمكان:\n"]

    for i, item in enumerate(results[:requested_count], 1):
        page_data = item.get("page_data", {}) or {}

        title = (
            page_data.get("program_name")
            or page_data.get("product_name")
            or page_data.get("place_name")
            or page_data.get("headline")
            or page_data.get("title")
            or item.get("source_title")
            or "بدون عنوان"
        )

        institution = page_data.get("institution_name") or ""
        summary = page_data.get("summary") or ""
        url = item.get("source_url") or ""

        degree_level = page_data.get("degree_level") or ""
        country = page_data.get("country") or ""
        city = page_data.get("city") or ""
        language_of_instruction = page_data.get("language_of_instruction") or ""
        requires_ielts_or_toefl = page_data.get("requires_ielts_or_toefl") or ""
        tuition = page_data.get("tuition") or ""
        deadline = page_data.get("deadline") or ""
        application_url = page_data.get("application_url") or ""
        official_program_url = page_data.get("official_program_url") or ""

        title = str(title).strip()
        institution = str(institution).strip()
        summary = str(summary).strip()
        url = str(url).strip()
        degree_level = str(degree_level).strip()
        country = str(country).strip()
        city = str(city).strip()
        language_of_instruction = localize_display_value(language_of_instruction, "language")
        requires_ielts_or_toefl = localize_display_value(requires_ielts_or_toefl, "ielts")
        tuition = localize_display_value(tuition, "tuition")
        deadline = localize_display_value(deadline, "deadline")
        application_url = localize_display_value(application_url, "url")
        official_program_url = localize_display_value(official_program_url, "url")

        lines.append(f"{i}. {title}")

        if institution:
            lines.append(f"الجامعة: {institution}")

        meta_parts = []
        if degree_level:
            meta_parts.append(f"الدرجة: {degree_level}")
        if country:
            meta_parts.append(f"الدولة: {country}")
        if city:
            meta_parts.append(f"المدينة: {city}")

        if meta_parts:
            lines.append(" | ".join(meta_parts))

        if summary:
            lines.append(f"الملخص: {summary}")
            
        important_points = []

        important_points.append(
            f"لغة الدراسة: {localize_display_value(language_of_instruction, 'language') if language_of_instruction else 'غير واضحة'}"
        )
        important_points.append(
            f"IELTS/TOEFL: {localize_display_value(requires_ielts_or_toefl, 'ielts') if requires_ielts_or_toefl else 'غير واضح'}"
        )
        important_points.append(
            f"الرسوم: {localize_display_value(tuition, 'tuition') if tuition else 'غير مذكورة بوضوح'}"
        )
        important_points.append(
            f"الموعد النهائي: {localize_display_value(deadline, 'deadline') if deadline else 'غير مذكور بوضوح'}"
        )

        if important_points:
            lines.append("نقاط مهمة:")
            for point in important_points:
                lines.append(f"- {point}")

        if official_program_url:
            lines.append(f"رابط البرنامج: {official_program_url}")
        if application_url:
            lines.append(f"رابط التقديم: {application_url}")
        elif not official_program_url and url:
            lines.append(f"الرابط: {url}")

        lines.append("")

    return "\n".join(lines)  





# هاي الدالة بتختار أفضل نتيجة وحدة وبتعطي سبب مختصر وواضح ليش انختارت.
def build_winner_summary(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> str:
    if not results:
        return "[think] ما لقيت نتيجة واضحة أقدر أختارها كأفضل خيار."

    def localize_value(value: Any, field_type: str = "") -> str:
        if isinstance(value, dict):
            if field_type == "deadline":
                parts = []
                for k, v in value.items():
                    key = str(k).replace("_", " ").strip()
                    val = str(v).strip()
                    if val:
                        parts.append(f"{key}: {val}")
                return " | ".join(parts) if parts else "غير مذكور بوضوح"
            value = str(value)

        if isinstance(value, list):
            value = " | ".join(str(x).strip() for x in value if str(x).strip())

        value = str(value or "").strip()
        lowered = value.lower()

        unknown_values = {
            "unknown",
            "not specified",
            "not specified.",
            "not specified in the provided text",
            "not specified in the provided text.",
            "n/a",
            "none",
            "no especificado",
            "no especificado en la página",
            "no especificado en la página.",
            "no especificado en la pagina",
            "no especificado en la pagina.",
            "desconocido"
        }

        if field_type == "deadline" and value.startswith("{") and value.endswith("}"):
            try:
                parsed = json.loads(value.replace("'", '"'))
                if isinstance(parsed, dict):
                    parts = []
                    for k, v in parsed.items():
                        key = str(k).replace("_", " ").strip()
                        val = str(v).strip()
                        if val:
                            parts.append(f"{key}: {val}")
                    return " | ".join(parts) if parts else "غير مذكور بوضوح"
            except Exception:
                pass

        if lowered in unknown_values:
            if field_type == "tuition":
                return "غير مذكورة بوضوح"
            if field_type == "deadline":
                return "غير مذكور بوضوح"
            return "غير واضح"

        if lowered in {"yes", "true", "required"}:
            return "نعم"

        if lowered in {"no", "false", "not required"}:
            return "لا"

        return value

    winner = results[0]
    page_data = winner.get("page_data", {}) or {}

    title = (
        page_data.get("program_name")
        or page_data.get("product_name")
        or page_data.get("place_name")
        or page_data.get("headline")
        or page_data.get("title")
        or winner.get("source_title")
        or "بدون عنوان"
    )

    institution = str(page_data.get("institution_name") or "").strip()
    summary = str(page_data.get("summary") or "").strip()
    url = str(page_data.get("official_program_url") or winner.get("source_url") or "").strip()

    language_of_instruction = localize_value(page_data.get("language_of_instruction"), "language")
    requires_ielts_or_toefl = localize_value(page_data.get("requires_ielts_or_toefl"), "ielts")
    tuition = localize_value(page_data.get("tuition"), "tuition")
    deadline = localize_value(page_data.get("deadline"), "deadline")

    reasons = []

    if preference.get("best_only"):
        reasons.append("اخترته لأنه من أوضح وأقوى النتائج الرسمية المتوفرة")
    if preference.get("cheapest_only"):
        reasons.append("اخترته لأنه ظهر كأفضل خيار متاح من ناحية الرسوم أو وضوح تكلفة الدراسة")
    if preference.get("no_ielts"):
        reasons.append("اخترته لأنه يبدو الأنسب من ناحية شرط IELTS/TOEFL")
    if preference.get("english_only"):
        reasons.append("اخترته لأنه مناسب من ناحية لغة الدراسة")

    if language_of_instruction and language_of_instruction != "غير واضح":
        reasons.append(f"لغة الدراسة: {language_of_instruction}")
    if requires_ielts_or_toefl and requires_ielts_or_toefl != "غير واضح":
        reasons.append(f"IELTS/TOEFL: {requires_ielts_or_toefl}")
    if tuition and tuition != "غير مذكورة بوضوح":
        reasons.append(f"الرسوم: {tuition}")
    if deadline and deadline != "غير مذكور بوضوح":
        reasons.append(f"الموعد النهائي: {deadline}")

    lines = ["[think] اخترت لك هذا الخيار:\n"]
    lines.append(f"البرنامج: {str(title).strip()}")

    if institution:
        lines.append(f"الجامعة: {institution}")

    if summary:
        lines.append(f"الملخص: {summary}")

    if reasons:
        lines.append("سبب الاختيار:")
        for reason in reasons:
            lines.append(f"- {reason}")

    if url:
        lines.append(f"الرابط: {url}")

    return "\n".join(lines)




# هاي الدالة بتفلتر النتائج حسب طلب المستخدم، مثل بدون IELTS أو فقط الإنجليزية.
def filter_research_results(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> List[Dict[str, Any]]:
    filtered = []

    for item in results:
        page_data = item.get("page_data", {}) or {}

        language_of_instruction = str(page_data.get("language_of_instruction") or "").strip().lower()
        requires_ielts_or_toefl = str(page_data.get("requires_ielts_or_toefl") or "").strip().lower()
        ielts_status = classify_ielts_requirement(requires_ielts_or_toefl)
        source_url = str(item.get("source_url") or "").strip().lower()

        if preference.get("english_only"):
            if "english" not in language_of_instruction and "الإنجليزية" not in language_of_instruction and "الانجليزية" not in language_of_instruction:
                continue

        if preference.get("no_ielts"):
            if ielts_status != "no":
                continue

        if preference.get("official_only"):
            if not is_official_source_url(source_url, research_type="education"):
                continue

        filtered.append(item)

    return filtered





# هاي الدالة بترتب النتائج بشكل بسيط حسب طلب المستخدم: أفضل أو أرخص.
def rank_research_results(results: List[Dict[str, Any]], preference: Dict[str, Any]) -> List[Dict[str, Any]]:
    def result_score(item: Dict[str, Any]) -> tuple:
        page_data = item.get("page_data", {}) or {}

        source_url = str(item.get("source_url") or "").strip().lower()
        institution = str(page_data.get("institution_name") or "").strip()
        program = str(page_data.get("program_name") or "").strip()
        tuition = str(page_data.get("tuition") or "").strip().lower()
        tuition_value = parse_tuition_value(tuition)
        ielts_status = classify_ielts_requirement(page_data.get("requires_ielts_or_toefl") or "")

        official_score = 1 if is_official_source_url(source_url, research_type="education") else 0
        metadata_score = 0
        if institution:
            metadata_score += 1
        if program:
            metadata_score += 1
        if tuition:
            metadata_score += 1

        if preference.get("cheapest_only"):
            return (
                int(tuition_value),
                -int(official_score),
                -int(metadata_score)
            )

        if preference.get("no_ielts"):
            ielts_rank = {
                "no": 2,
                "unknown": 1,
                "yes": 0
            }.get(ielts_status, 0)

            return (
                int(official_score),
                int(ielts_rank),
                int(metadata_score)
            )

        return (
            int(official_score),
            int(metadata_score)
        )
    
    if preference.get("cheapest_only"):
        return sorted(results, key=result_score)

    return sorted(results, key=result_score, reverse=True)



    # هاي الدالة بتفهم حالة IELTS/TOEFL بشكل أوضح: مؤكد لا، مؤكد نعم، أو غير واضح.
def classify_ielts_requirement(value: str) -> str:
    text = str(value or "").strip().lower()

    if text in ["false", "no", "لا", "not required", "not needed"]:
        return "no"

    if text in ["true", "yes", "نعم", "required", "needed"]:
        return "yes"

    return "unknown"




# هاي الدالة بتحاول تطلع رقم تقريبي من حقل الرسوم حتى نقدر نرتب الأرخص بشكل أحسن.
# هاي الدالة بتحاول تطلع رقم من الرسوم، وإذا ما قدرت بترجع رقم كبير جدًا بدل ما ترجع None أو تخرب الفرز.
def parse_tuition_value(tuition_text: str) -> float:
    text = str(tuition_text or "").strip().lower()

    if not text:
        return 999999999.0

    cleaned = (
        text.replace(",", "")
        .replace("€", "")
        .replace("$", "")
        .replace("eur", "")
        .replace("usd", "")
    )

    match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
    if not match:
        return 999999999.0

    try:
        return float(match.group(1))
    except Exception:
        return 999999999.0





# هاي الدالة بتحاول تميز إذا الرابط غالباً رسمي أو تابع لجهة أصلية، وبتستبعد روابط التجميع والمواقع العامة.
def is_official_source_url(url: str, research_type: str = "general") -> bool:
    if not url:
        return False

    lowered_url = url.lower()

    blocked_domains = [
        "educations.com",
        "educations.es",
        "mastersportal.com",
        "masterstudies.com",
        "findamasters.com",
        "studyportals.com",
        "bachelorstudies.com",
        "phdstudies.com",
        "financialmagazine.es",
        "universoptimum.com",
        "yaq.es",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "medium.com",
        "reddit.com",
        "quora.com",
        "wikipedia.org",
        "topuniversities.com",
        "timeshighereducation.com",
        "shiksha.com",
        "ielts.org",
        "ielts.idp.com",
    ]

    if any(domain in lowered_url for domain in blocked_domains):
        return False

    if research_type == "education":
        official_hints = [
            ".edu", ".ac.", ".ac.uk",
            "universidad", "university",
            "/master", "/masters", "/graduate", "/admissions", "/program",
            "/postgrado", "/estudio", "/degree", "/degrees"
        ]

        # إذا الرابط فيه مؤشرات أكاديمية/برامج، اعتبره مرشح رسمي
        if any(hint in lowered_url for hint in official_hints):
            return True

        # إذا الدومين يبدو تابعًا لموقع رسمي أوروبي/جامعي وليس من المواقع المحظورة
        if lowered_url.startswith("https://www.") or lowered_url.startswith("https://"):
            if ".es/" in lowered_url or lowered_url.endswith(".es") or ".edu/" in lowered_url:
                return True

        return False

    if research_type == "travel":
        official_hints = [
            ".gov", ".gob", ".eu",
            "official", "visit", "tourism",
            "booking.com", "airbnb.com", "expedia.com"
        ]
        return any(hint in lowered_url for hint in official_hints)

    if research_type == "product":
        official_hints = [
            "amazon.", "mediamarkt.", "coolblue.", "bol.", "apple.", "sony.", "dell.", "ikea."
        ]
        return any(hint in lowered_url for hint in official_hints)

    if research_type == "news":
        official_hints = [
            ".com", ".org", ".net"
        ]
        return any(hint in lowered_url for hint in official_hints)

    return True

