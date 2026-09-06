"""Licensed artist-photo candidates from Wikimedia Commons."""
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote

import httpx


API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "FANHEAT-Artist-Collector/1.0 (https://fanheat.com)"
ALLOWED_LICENSE_MARKERS = ("cc by ", "cc by-sa", "cc-by-", "cc-by-sa", "cc0", "public domain")
DENIED_LICENSE_MARKERS = ("-nc", " nc ", "noncommercial", "-nd", " no derivatives")


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def _text(value) -> str:
    parser = _PlainText()
    parser.feed(unescape(str(value or "")))
    return " ".join(parser.parts).strip()[:500]


def _api(url, params):
    response = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()


def _metadata_value(metadata, key):
    value = metadata.get(key) or {}
    return value.get("value") if isinstance(value, dict) else value


def _allowed_license(name: str, url: str) -> bool:
    normalized = f" {name} {url} ".lower().replace("_", "-")
    return any(marker in normalized for marker in ALLOWED_LICENSE_MARKERS) and not any(marker in normalized for marker in DENIED_LICENSE_MARKERS)


def collect_commons_candidates(wikidata_id: str | None, limit: int, logs: list[str]) -> list[dict]:
    if not wikidata_id or not wikidata_id.startswith("Q") or not wikidata_id[1:].isdigit() or limit <= 0:
        logs.append("Wikimedia Commons 탐색 건너뜀 · 확인된 Wikidata 아티스트 ID 없음")
        return []
    entity_data = _api(WIKIDATA_API, {
        "action":"wbgetentities", "ids":wikidata_id, "props":"claims|sitelinks", "format":"json",
        "sitefilter":"commonswiki",
    }).get("entities", {}).get(wikidata_id, {})
    claims = entity_data.get("claims", {})
    category_claim = (claims.get("P373") or [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    commons_title = entity_data.get("sitelinks", {}).get("commonswiki", {}).get("title", "")
    category = category_claim or (commons_title.removeprefix("Category:") if commons_title.startswith("Category:") else "")
    titles = []
    main_image = (claims.get("P18") or [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    if main_image:
        titles.append("File:" + str(main_image).removeprefix("File:"))
    if category:
        category_queue = ["Category:" + category]
        seen_categories = set()
        # Commons often stores the useful event/year photographs one or two
        # categories below the artist category. Traverse a small bounded tree.
        while category_queue and len(seen_categories) < 10 and len(titles) < 50:
            current = category_queue.pop(0)
            if current in seen_categories:
                continue
            seen_categories.add(current)
            members = _api(API, {
                "action":"query", "list":"categorymembers", "cmtitle":current,
                "cmtype":"file|subcat", "cmlimit":50, "format":"json",
            }).get("query", {}).get("categorymembers", [])
            for row in members:
                title = row.get("title", "")
                if row.get("ns") == 6 or title.startswith("File:"):
                    titles.append(title)
                elif row.get("ns") == 14 or title.startswith("Category:"):
                    category_queue.append(title)
    titles = list(dict.fromkeys(titles))[:50]
    if not titles:
        logs.append(f"Wikimedia Commons 파일 미확인 · {wikidata_id}")
        return []
    accepted = []
    for start in range(0, len(titles), 20):
        pages = _api(API, {
            "action":"query", "prop":"imageinfo", "titles":"|".join(titles[start:start + 20]),
            "iiprop":"url|mime|extmetadata", "iiurlwidth":1600, "iiextmetadatalanguage":"ko",
            "iiextmetadatafilter":"LicenseShortName|LicenseUrl|Artist|Credit|Attribution|UsageTerms|Restrictions|DateTimeOriginal",
            "format":"json", "formatversion":2,
        }).get("query", {}).get("pages", [])
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            metadata = info.get("extmetadata") or {}
            license_name = _text(_metadata_value(metadata, "LicenseShortName") or _metadata_value(metadata, "UsageTerms"))
            license_url = str(_metadata_value(metadata, "LicenseUrl") or "").strip()
            creator = _text(_metadata_value(metadata, "Artist") or _metadata_value(metadata, "Credit") or _metadata_value(metadata, "Attribution"))
            if not _allowed_license(license_name, license_url) or not creator:
                logs.append(f"Commons 제외: 라이선스 또는 촬영자 표기 불충분 · {page.get('title', '')}")
                continue
            source_page = info.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + quote(page.get("title", "").replace(" ", "_"), safe=":()_-.")
            image_url = info.get("thumburl") or info.get("url")
            original_url = info.get("url")
            if not image_url or not original_url:
                continue
            attribution = f"{creator} · {license_name} · Wikimedia Commons"
            accepted.append({
                "image_url":image_url, "source_url":source_page, "original_image_url":original_url,
                "source_provider":"wikimedia_commons", "creator_name":creator,
                "license_name":license_name, "license_url":license_url or source_page,
                "attribution_text":attribution, "captured_on":_text(_metadata_value(metadata, "DateTimeOriginal"))[:10] or None,
            })
            if len(accepted) >= limit:
                break
        if len(accepted) >= limit:
            break
    logs.append(f"Wikimedia Commons 재사용 후보 {len(accepted)}개 · 촬영자와 허용 라이선스 확인")
    return accepted
