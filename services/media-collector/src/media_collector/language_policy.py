import re

from .schemas import CollectionRequest, LanguageFilterMode, MediaContent


OFFICIAL_KPOP_CHANNEL_MARKERS = (
    "1thek",
    "bangtantv",
    "hybe labels",
    "jyp entertainment",
    "jypentertainment",
    "kbs kpop",
    "kbs world",
    "mbc kpop",
    "mbckpop",
    "mnet k-pop",
    "mnet kpop",
    "sbs kpop",
    "smtown",
    "starshiptv",
    "studio choom",
    "the k-pop",
    "weverse",
    "yg entertainment",
    "뮤직뱅크",
    "엠카운트다운",
    "인기가요",
)

LANGUAGE_WORDS = {
    "en": (" the ", " and ", " with ", " from ", " this ", " live ", " official "),
    "es": (" el ", " la ", " de ", " con ", " para ", " una ", " en "),
    "pt": (" de ", " do ", " da ", " com ", " para ", " uma ", " em "),
    "de": (" der ", " die ", " das ", " mit ", " für ", " und ", " von "),
    "fr": (" le ", " la ", " les ", " avec ", " pour ", " une ", " des "),
    "id": (" yang ", " dan ", " dengan ", " untuk ", " dari ", " ini "),
    "vi": (" và ", " của ", " với ", " cho ", " trong ", " một "),
}


def apply_language_policy(items: list[MediaContent], request: CollectionRequest) -> list[MediaContent]:
    """Rank or filter connector results using the requested metadata language.

    YouTube's relevanceLanguage and regionCode are ranking hints rather than hard
    filters. This policy is intentionally applied after the upstream search.
    """
    if not items:
        return []
    language = (request.language_code or "").split("-", 1)[0].lower()
    if not language:
        return items[: request.max_results]

    ranked = []
    for index, item in enumerate(items):
        score, matches_language = language_affinity(item, language)
        official_kpop = is_official_kpop_channel(item)
        if official_kpop:
            score += 7
        ranked.append((matches_language, score, -index, item))

    mode = request.language_filter_mode or LanguageFilterMode.PREFER
    if mode == LanguageFilterMode.STRICT:
        ranked = [entry for entry in ranked if entry[0]]
    ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
    return [entry[3] for entry in ranked[: request.max_results]]


def language_affinity(item: MediaContent, language: str) -> tuple[int, bool]:
    title = item.title or ""
    description = item.text or ""
    channel = item.author.name or ""
    combined = f" {title} {description} {channel} ".lower()

    if language == "ko":
        title_count = len(re.findall(r"[가-힣]", title))
        description_count = len(re.findall(r"[가-힣]", description))
        channel_count = len(re.findall(r"[가-힣]", channel))
        matches = title_count >= 2 or channel_count >= 2 or description_count >= 5
        return title_count * 3 + channel_count * 2 + min(description_count, 10), matches

    if language == "ja":
        title_count = len(re.findall(r"[ぁ-ゖァ-ヺ]", title))
        combined_count = len(re.findall(r"[ぁ-ゖァ-ヺ]", combined))
        matches = title_count >= 2 or combined_count >= 5
        return title_count * 3 + min(combined_count, 10), matches

    if language == "zh":
        title_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", title))
        combined_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", combined))
        has_japanese_kana = bool(re.search(r"[ぁ-ゖァ-ヺ]", combined))
        matches = not has_japanese_kana and (title_count >= 2 or combined_count >= 5)
        return title_count * 3 + min(combined_count, 10), matches

    words = LANGUAGE_WORDS.get(language, ())
    hits = sum(combined.count(word) for word in words)
    matches = hits >= 2
    return hits * 4, matches


def is_official_kpop_channel(item: MediaContent) -> bool:
    channel = (item.author.name or "").casefold()
    return any(marker in channel for marker in OFFICIAL_KPOP_CHANNEL_MARKERS)
