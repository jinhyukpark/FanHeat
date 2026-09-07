import hashlib
import ipaddress
import json
import re
import socket
import unicodedata
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, timezone


class ImportLog(list):
    """Persist progress independently, so the UI can poll during network I/O."""
    def __init__(self, db, job_id):
        super().__init__()
        self.bind, self.job_id = db.get_bind(), job_id

    def append(self, message):
        super().append(message)
        if not self.job_id:
            return
        from .models import CollectionJob
        with Session(self.bind) as session:
            job = session.get(CollectionJob, self.job_id)
            if not job or job.source != "artist":
                return
            if job.status == "cancelled":
                raise RuntimeError("관리자가 수집을 중지했습니다.")
            cursor = json.loads(job.cursor or "{}")
            entries = cursor.get("logs", [])
            entries.append({"at": datetime.now(timezone.utc).isoformat(), "level": "info", "message": str(message)[:1000]})
            cursor.update(logs=entries[-2000:], stage=str(message)[:100], progress=50)
            job.cursor = json.dumps(cursor, ensure_ascii=False)
            session.commit()


SOCIAL_DOMAINS = {
    "facebook.com": "facebook_url",
    "instagram.com": "instagram_url",
    "x.com": "x_url",
    "twitter.com": "x_url",
}

WIKIDATA_SOCIAL_CLAIMS = {
    "P856": lambda value: value,
    "P2397": lambda value: f"https://www.youtube.com/channel/{value}",
    "P2003": lambda value: f"https://www.instagram.com/{value}",
    "P2002": lambda value: f"https://x.com/{value}",
    "P7085": lambda value: f"https://www.tiktok.com/@{value}",
    "P2013": lambda value: f"https://www.facebook.com/{value}",
}


class ArtistPageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.images: list[str] = []
        self.json_ld: list[dict | list] = []
        self.in_json_ld = False
        self.json_ld_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, content)
        if tag.lower() == "a" and values.get("href"):
            self.links.append(urljoin(self.base_url, values["href"]))
        if tag.lower() == "img":
            # Official sites frequently lazy-load their photographic galleries.
            # Keep every declared source and let the vision stage decide whether
            # it is an artist photo, rather than silently losing data-* images.
            for key in ("src", "data-src", "data-original", "data-lazy-src"):
                if values.get(key):
                    self.images.append(urljoin(self.base_url, values[key]))
            for source in values.get("srcset", "").split(","):
                candidate = source.strip().split(" ", 1)[0]
                if candidate:
                    self.images.append(urljoin(self.base_url, candidate))
        if tag.lower() == "script" and "ld+json" in values.get("type", "").lower():
            self.in_json_ld = True
            self.json_ld_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        if tag.lower() == "script" and self.in_json_ld:
            self.in_json_ld = False
            try:
                value = json.loads("".join(self.json_ld_buffer))
                if isinstance(value, (dict, list)):
                    self.json_ld.append(value)
            except (TypeError, ValueError):
                pass

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_json_ld:
            self.json_ld_buffer.append(data)


def _public_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("official source URLs must use HTTPS")
    addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("official source URL resolved to a non-public address")


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized or f"artist-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def _search_key(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "", unicodedata.normalize("NFKC", value).casefold())


def _claim_values(entity: dict, property_id: str) -> list[str]:
    values = []
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _claim_entity_ids(entity: dict, property_id: str) -> set[str]:
    ids = set()
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            ids.add(value["id"])
    return ids


def _current_claim_entity_ids(entity: dict, property_id: str) -> set[str]:
    ids = set()
    for claim in entity.get("claims", {}).get(property_id, []):
        if claim.get("rank") == "deprecated" or claim.get("qualifiers", {}).get("P582"):
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            ids.add(value["id"])
    return ids


def _claim_raw_values(entity: dict, property_id: str) -> list:
    return [claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            for claim in entity.get("claims", {}).get(property_id, [])
            if claim.get("mainsnak", {}).get("datavalue", {}).get("value") is not None]


def _localized_claim_text(entity: dict, property_id: str, language: str) -> str | None:
    values = _claim_raw_values(entity, property_id)
    localized = next((value.get("text") for value in values
                      if isinstance(value, dict) and value.get("language") == language and value.get("text")), None)
    return localized or next((value.get("text") for value in values
                              if isinstance(value, dict) and value.get("text")), None)


def _claim_date(entity: dict, *property_ids: str) -> str | None:
    for property_id in property_ids:
        for value in _claim_raw_values(entity, property_id):
            raw = value.get("time", "") if isinstance(value, dict) else ""
            match = re.match(r"^[+-](\d{4})-(\d{2})-(\d{2})", raw)
            if match:
                year, month, day = match.groups()
                return year if month == "00" else f"{year}-{month}" if day == "00" else f"{year}-{month}-{day}"
    return None


def _commons_source_url(entity: dict, artist_name: str) -> str:
    category = next(iter(_claim_values(entity, "P373")), "")
    title = entity.get("sitelinks", {}).get("commonswiki", {}).get("title", "")
    if category:
        return "https://commons.wikimedia.org/wiki/Category:" + quote(category.replace(" ", "_"), safe="()_-.")
    if title:
        return "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":()_-.")
    return "https://commons.wikimedia.org/wiki/Special:MediaSearch?type=image&search=" + quote(artist_name)


COUNTRY_ENTITY_IDS = {
    "KR": {"Q884"},
    "JP": {"Q17"},
    "US": {"Q30"},
    "GB": {"Q145"},
}


def source_url_region(url: str) -> str | None:
    """Return a region only when a URL is explicitly localized."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    value = f"{hostname}{parsed.path.casefold()}"
    if hostname.endswith(".jp") or re.search(r"(?:^|[._/-])(?:jp|japan|japanese)(?:[._/-]|$)", value):
        return "JP"
    if hostname.endswith(".kr") or re.search(r"(?:^|[._/-])(?:kr|korea|korean)(?:[._/-]|$)", value):
        return "KR"
    if hostname.endswith(".uk") or re.search(r"(?:^|[._/-])(?:uk|britain|british)(?:[._/-]|$)", value):
        return "GB"
    return None


def source_url_allowed_for_region(url: str, country_code: str) -> bool:
    explicit_region = source_url_region(url)
    return explicit_region is None or explicit_region == country_code


def search_artist_candidates(
    artist_name: str,
    language_code: str = "ko",
    timeout: float = 20,
    *,
    country_code: str = "KR",
    search_region: str = "domestic",
) -> list[dict]:
    """Identity preview only: never creates a job or picks a result automatically."""
    language = language_code.split('-')[0]
    search_languages = [language]
    if search_region == "global":
        search_languages.extend(["en", "ko", "ja"])
    search_languages = list(dict.fromkeys(search_languages))
    with httpx.Client(timeout=timeout, headers={"User-Agent": "FANHEAT-Artist-Collector/1.0"}) as client:
        hits_by_id = {}
        for search_language in search_languages:
            response = client.get('https://www.wikidata.org/w/api.php', params={
                'action': 'wbsearchentities', 'search': artist_name, 'language': search_language,
                'uselang': language, 'format': 'json', 'limit': 8, 'type': 'item'})
            response.raise_for_status()
            for hit in response.json().get('search', []):
                if re.fullmatch(r'Q\d+', hit.get('id', '')):
                    hits_by_id.setdefault(hit['id'], hit)
        hits = list(hits_by_id.values())[:16]
        if not hits:
            return []
        response = client.get('https://www.wikidata.org/w/api.php', params={
            'action': 'wbgetentities', 'ids': '|'.join(h['id'] for h in hits),
            'props': 'labels|descriptions|claims|sitelinks', 'languages': f'{language}|en', 'sitefilter': 'commonswiki', 'format': 'json'})
        response.raise_for_status()
        entities = response.json().get('entities', {})
        related_ids = set()
        for entity in entities.values():
            for property_id in ("P106", "P108", "P264"):
                related_ids.update(_claim_entity_ids(entity, property_id))
        related_entities = {}
        if related_ids:
            response = client.get('https://www.wikidata.org/w/api.php', params={
                'action': 'wbgetentities', 'ids': '|'.join(sorted(related_ids)), 'props': 'labels',
                'languages': f'{language}|en|ko|ja', 'format': 'json'})
            response.raise_for_status()
            related_entities = response.json().get('entities', {})
    candidates = []
    preferred_country_ids = COUNTRY_ENTITY_IDS.get(country_code, set())
    for hit in hits:
        entity = entities.get(hit['id'], {})
        entity_country_ids = _claim_entity_ids(entity, "P27") | _claim_entity_ids(entity, "P495")
        country_match = bool(preferred_country_ids & entity_country_ids)
        urls = []
        for prop, builder in WIKIDATA_SOCIAL_CLAIMS.items():
            for value in _claim_values(entity, prop):
                url = builder(value)
                parsed = urlparse(url)
                if parsed.scheme == 'http':
                    url = parsed._replace(scheme='https').geturl()
                if urlparse(url).scheme == 'https':
                    urls.append(url)
        if search_region == "domestic":
            urls = [url for url in urls if source_url_allowed_for_region(url, country_code)]
        labels = entity.get('labels', {})
        descriptions = entity.get('descriptions', {})
        def related_labels(property_ids, *, current=False):
            values = []
            for property_id in property_ids:
                claim_ids = _current_claim_entity_ids(entity, property_id) if current else _claim_entity_ids(entity, property_id)
                for entity_id in claim_ids:
                    related = related_entities.get(entity_id, {}).get('labels', {})
                    label = (related.get(language, {}) or related.get('ko', {}) or related.get('en', {}) or {}).get('value')
                    if label:
                        values.append(label)
            return list(dict.fromkeys(values))
        agency_labels = related_labels(('P108', 'P264'), current=True)
        profile_facts = {
            'official_name': _localized_claim_text(entity, 'P1448', language),
            'real_name': (_localized_claim_text(entity, 'P1477', language)
                          or ((labels.get(language, {}) or labels.get('ko', {})).get('value')
                              if 'Q5' in _claim_entity_ids(entity, 'P31') else None)),
            'debut_text': _claim_date(entity, 'P2031', 'P571'),
            'role_description': ' · '.join(related_labels(('P106',))) or None,
            'agency': agency_labels[0] if len(agency_labels) == 1 else None,
            'agency_candidates': agency_labels,
        }
        candidates.append({'id': hit['id'], 'label': labels.get(language, {}).get('value') or hit.get('label') or hit['id'],
            'english_name': labels.get('en', {}).get('value'),
            'description': descriptions.get(language, {}).get('value') or descriptions.get('en', {}).get('value') or hit.get('description') or '설명 정보 없음',
            'entity_url': f"https://www.wikidata.org/wiki/{hit['id']}",
            'commons_source_url': _commons_source_url(entity, artist_name),
            'official_source_urls': list(dict.fromkeys(urls))[:20],
            'profile_facts': profile_facts,
            'country_match': country_match})
    if search_region == "domestic":
        candidates.sort(key=lambda candidate: not candidate['country_match'])
    return candidates


def discover_artist_sources(
    artist_name: str,
    *,
    language_code: str = "ko",
    country_code: str = "KR",
    youtube_api_key: str | None = None,
    timeout: float = 20,
) -> dict:
    """Discover likely official channels without silently accepting an ambiguous identity."""
    target = _search_key(artist_name)
    logs = [f"Wikidata에서 ‘{artist_name}’ 아티스트 후보 검색 시작"]
    candidates = []
    with httpx.Client(timeout=timeout, headers={"User-Agent": "FANHEAT-Artist-Collector/1.0"}) as client:
        response = client.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": artist_name,
                "language": language_code.split("-")[0],
                "uselang": language_code.split("-")[0],
                "format": "json",
                "limit": 8,
                "type": "item",
            },
        )
        response.raise_for_status()
        for item in response.json().get("search", []):
            names = [item.get("label", ""), *item.get("aliases", [])]
            ratios = [SequenceMatcher(None, target, _search_key(name)).ratio() for name in names if name]
            score = max(ratios, default=0.0) * 0.9
            description = str(item.get("description") or "")
            if any(word in description.casefold() for word in ("singer", "musician", "band", "group", "가수", "음악")):
                score = min(1.0, score + 0.1)
            if any(word in description.casefold() for word in ("template", "위키백과 틀", "동음이의")):
                score = max(0.0, score - 0.3)
            candidates.append({"id": item.get("id"), "label": item.get("label"), "description": description, "score": score})
        candidates.sort(key=lambda item: item["score"], reverse=True)
        top = candidates[0] if candidates else None
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
        urls = []
        if top and top.get("id"):
            logs.append(f"Wikidata 후보 확인: {top['label']} · 일치도 {round(top['score'] * 100)}%")
            entity_response = client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{top['id']}.json")
            entity_response.raise_for_status()
            entity = entity_response.json().get("entities", {}).get(top["id"], {})
            for property_id, url_builder in WIKIDATA_SOCIAL_CLAIMS.items():
                for value in _claim_values(entity, property_id):
                    urls.append(url_builder(value))
        if youtube_api_key:
            logs.append("YouTube Data API에서 공식 채널 후보 확인")
            youtube_response = client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "type": "channel",
                    "maxResults": 5,
                    "q": f"{artist_name} official",
                    "regionCode": country_code,
                    "key": youtube_api_key,
                },
            )
            youtube_response.raise_for_status()
            youtube_candidates = youtube_response.json().get("items", [])
            if youtube_candidates:
                channel = youtube_candidates[0]
                channel_id = channel.get("snippet", {}).get("channelId") or channel.get("id", {}).get("channelId")
                channel_title = channel.get("snippet", {}).get("channelTitle") or channel.get("snippet", {}).get("title")
                if channel_id:
                    logs.append(f"YouTube 검색 후보 (공식성 미확인, 자동 채택 안 함): {channel_title or channel_id}")
        urls = list(dict.fromkeys(url for url in urls if urlparse(url).scheme == "https"))
        confidence = float(top["score"]) if top else 0.0
        ambiguous = not urls or confidence < 0.78 or (second_score and confidence - second_score < 0.08)
        if urls:
            logs.extend(f"공식 출처 후보 발견: {url}" for url in urls)
        if ambiguous:
            logs.append("이름만으로 공식 아티스트를 안전하게 확정하지 못해 수집을 일시 정지합니다.")
        else:
            logs.append(f"공식 출처 후보 {len(urls)}개를 확인하여 수집 단계로 전달합니다.")
        return {
            "official_source_urls": urls,
            "confidence": round(confidence, 4),
            "ambiguous": ambiguous,
            "can_collect": not ambiguous,
            "candidate": top,
            "candidates": candidates[:5],
            "logs": logs,
        }


def _absolute_image(value, base_url: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    if not isinstance(value, str) or not value.strip():
        return None
    url = urljoin(base_url, value.strip())
    return url if urlparse(url).scheme == "https" else None


def _walk_json_ld(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json_ld(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json_ld(nested)


def collect_artist_sources(urls: list[str], timeout: float = 20, logs: list[str] | None = None) -> list[dict]:
    """Isolate source failures; never send a request over plaintext HTTP."""
    logs = logs if logs is not None else []
    results = []
    for url in urls:
        try:
            pages = _collect_artist_source(url, timeout, logs)
            if pages:
                results.extend(pages)
                logs.append(f"출처 수집 완료: {pages[0]['url']}")
            else:
                logs.append(f"출처 건너뜀 (HTML 콘텐츠 없음): {url}")
        except (httpx.HTTPError, OSError, ValueError) as exc:
            reason = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else str(exc)[:200]
            logs.append(f"출처 수집 건너뜀: {url} · {reason}")
    if not results:
        raise ValueError("수집 가능한 공식 출처가 없습니다. " + " / ".join(logs[-20:]))
    return results


def collect_gallery_pages(pages: list[dict], logs: list[str], max_pages: int = 24) -> list[dict]:
    """Follow photographic sections on the verified official web origins only."""
    roots = {urlparse(page["url"]).hostname for page in pages
             if (urlparse(page["url"]).hostname or "").lower() not in {
                 "youtube.com", "www.youtube.com", "instagram.com", "www.instagram.com",
                 "facebook.com", "www.facebook.com", "x.com", "www.x.com", "twitter.com", "www.twitter.com"}}
    visited = {page["url"].split("#", 1)[0] for page in pages}
    patterns = (
        re.compile(r"gallery|photo|画像|フォト|profile|member|artist|news|media|press", re.I),
        re.compile(r"schedule|shop|store|goods|merch|ticket|discograph|album|release", re.I),
    )
    candidates: list[tuple[int, str]] = []
    for page in pages:
        for link in page.get("links", []):
            clean = link.split("#", 1)[0]
            parsed = urlparse(clean)
            if parsed.scheme != "https" or parsed.hostname not in roots or clean in visited:
                continue
            haystack = f"{parsed.path}?{parsed.query}"
            if patterns[0].search(haystack) and not patterns[1].search(haystack):
                priority = 0 if re.search(r"gallery|photo|画像|フォト|profile|member", haystack, re.I) else 1
                candidates.append((priority, clean))
    added = []
    for _, url in sorted(dict.fromkeys(candidates))[:max_pages]:
        visited.add(url)
        try:
            children = _collect_artist_source(url, 15, logs)
            added.extend(children)
            logs.append(f"공식 사진 페이지 탐색: {url} · 이미지 {sum(len(p.get('images', [])) for p in children)}개")
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logs.append(f"공식 사진 페이지 건너뜀: {url} · {str(exc)[:120]}")
    # Put dedicated photo/profile pages first so a homepage full of album art or
    # banners cannot consume the entire vision-review budget.
    return [*added, *pages]


def _collect_artist_source(url: str, timeout: float, logs: list[str]) -> list[dict]:
    results = []
    with httpx.Client(follow_redirects=False, timeout=timeout, headers={"User-Agent": "FANHEAT-Artist-Collector/1.0"}) as client:
        for url in [url]:
            current_url = url
            for _ in range(6):
                _public_https_url(current_url)
                response = client.get(current_url)
                if not response.is_redirect:
                    break
                location = response.headers.get("location")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                parsed = urlparse(current_url)
                if parsed.scheme == "http":
                    # Some official sites advertise legacy HTTP redirects. Try
                    # the secure equivalent, then validate it on the next hop.
                    current_url = parsed._replace(scheme="https").geturl()
                    logs.append(f"이동 주소를 HTTPS로 확인: {current_url}")
            else:
                raise ValueError("official source URL redirected too many times")
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                continue
            parser = ArtistPageParser(str(response.url))
            parser.feed(response.text[:2_000_000])
            images = [parser.meta.get("og:image"), parser.meta.get("twitter:image"), *parser.images]
            results.append({
                "html": response.text[:2_000_000],
                "url": str(response.url),
                "title": (parser.meta.get("og:title") or parser.title).strip()[:300],
                "description": (parser.meta.get("og:description") or parser.meta.get("description") or "").strip()[:5000],
                "images": list(dict.fromkeys(filter(None, (_absolute_image(image, str(response.url)) for image in images))))[:50],
                "links": list(dict.fromkeys(link for link in parser.links if urlparse(link).scheme == "https"))[:500],
                "json_ld": parser.json_ld[:30],
            })
    return results


def _social_values(pages: list[dict]) -> dict[str, str]:
    values: dict[str, str] = {}
    for url in [page["url"] for page in pages] + [link for page in pages for link in page["links"]]:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        for domain, field in SOCIAL_DOMAINS.items():
            if host == domain or host.endswith(f".{domain}"):
                values.setdefault(field, url)
    return values


def _music_albums(pages: list[dict], limit: int) -> list[dict]:
    albums = []
    for page in pages:
        for item in _walk_json_ld(page["json_ld"]):
            item_type = item.get("@type", "")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "MusicAlbum" not in types or not item.get("name"):
                continue
            tracks = []
            for track in item.get("track", []) if isinstance(item.get("track"), list) else []:
                if isinstance(track, dict) and track.get("name"):
                    tracks.append({"title": str(track["name"])[:300], "duration": track.get("duration"), "url": track.get("url")})
            release_value = str(item.get("datePublished") or "")
            release_match = re.match(r"^\d{4}-\d{2}-\d{2}", release_value)
            albums.append({
                "title": str(item["name"])[:200],
                "release_date": release_match.group(0) if release_match else None,
                "cover_url": _absolute_image(item.get("image"), page["url"]),
                "external_url": item.get("url") or page["url"],
                "tracks": tracks[:200],
            })
            if len(albums) >= limit:
                return albums
    return albums


def _save_artist_albums(db: Session, artist_id: int, albums: list[dict], scopes: set[str], active: bool) -> tuple[int, int]:
    from .artist_catalog import youtube_id
    album_count = track_count = 0
    if not scopes & {"albums", "tracks"}:
        return album_count, track_count
    for index, album in enumerate(albums, 1):
        album_row = db.execute(text("select id from public.artist_albums where artist_id=:artist_id and title=:title"), {"artist_id": artist_id, "title": album["title"]}).first()
        if album_row:
            album_id = album_row.id
            db.execute(text("""update public.artist_albums set cover_url=coalesce(cover_url,:cover),
                external_url=coalesce(external_url,:source), release_date=coalesce(release_date,cast(:released as date)),
                track_count=greatest(coalesce(track_count,0),:count) where id=:id"""),
                {"id": album_id, "cover": album.get("cover_url"), "source": album["external_url"],
                 "released": album.get("release_date"), "count": len(album["tracks"])})
        else:
            album_id = db.execute(text("""
                insert into public.artist_albums
                  (artist_id,title,release_date,track_count,cover_url,external_url,album_type,active,display_order)
                values (:artist_id,:title,cast(:release_date as date),:track_count,:cover_url,:external_url,:album_type,:active,:display_order)
                returning id
            """), {"artist_id": artist_id, "title": album["title"], "release_date": album["release_date"], "track_count": len(album["tracks"]), "cover_url": album["cover_url"], "external_url": album["external_url"], "album_type": album.get("album_type") or "미확인", "active": active, "display_order": index}).scalar_one()
            album_count += 1
        if "tracks" in scopes:
            for track_index, track in enumerate(album["tracks"], 1):
                inserted = db.execute(text("""
                    insert into public.artist_album_tracks
                      (album_id,track_number,title,duration_text,youtube_url,active,display_order)
                    values (:album_id,:track_number,:title,:duration_text,:youtube_url,:active,:display_order)
                    on conflict (album_id,track_number) do update
                      set youtube_url=coalesce(artist_album_tracks.youtube_url,excluded.youtube_url)
                      where artist_album_tracks.title=excluded.title returning id
                """), {"album_id": album_id, "track_number": track_index, "title": track["title"], "duration_text": track["duration"], "youtube_url": track["url"] if youtube_id(track.get("url") or "") else None, "active": active, "display_order": track_index}).first()
                track_count += int(inserted is not None)
    return album_count, track_count


def _official_fandom_name(pages: list[dict]) -> str | None:
    patterns = (
        r"팬덤명\s*[:：]\s*([A-Za-z0-9가-힣][A-Za-z0-9가-힣 .'-]{1,38})",
        r"official\s+fandom\s+name\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9 .'-]{1,38})",
    )
    for page in pages:
        host = (urlparse(page.get("url", "")).hostname or "").removeprefix("www.")
        if host in SOCIAL_DOMAINS or "youtube.com" in host:
            continue
        text_value = re.sub(r"<[^>]+>", " ", page.get("html", ""))
        for pattern in patterns:
            match = re.search(pattern, text_value, re.I)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip(" .")
    return None


def _direct_socials(urls: list[str]) -> dict[str, str]:
    values = {}
    for url in urls:
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.").removeprefix("m.")
        for domain, field in SOCIAL_DOMAINS.items():
            if host == domain or host.endswith("." + domain):
                values.setdefault(field, url)
    return values


def _fill_missing_artist_profile(db: Session, artist_id: int, values: dict) -> None:
    db.execute(text("""
        update public.artists set
          name=case when nullif(name,'') is null or name=name_ko then coalesce(:name,name) else name end,
          name_ko=coalesce(nullif(name_ko,''),:name_ko),
          real_name=coalesce(nullif(real_name,''),:real_name),
          role_description=coalesce(nullif(role_description,''),:role_description),
          debut_text=coalesce(nullif(debut_text,''),:debut_text),
          agency=coalesce(nullif(agency,''),:agency), fandom_name=coalesce(nullif(fandom_name,''),:fandom_name),
          facebook_url=coalesce(nullif(facebook_url,''),:facebook_url),
          x_url=coalesce(nullif(x_url,''),:x_url),
          instagram_url=coalesce(nullif(instagram_url,''),:instagram_url), updated_at=now()
        where id=:artist_id
    """), values | {"artist_id": artist_id})


def import_artist(db: Session, request: dict) -> dict:
    from .gallery_vision import classify_gallery, save_gallery_candidates, representative_photo
    from .artist_writing import draft_artist_sections, save_artist_sections
    from .artist_catalog import crawl_catalog, connect_youtube, youtube_id, profile_and_news
    from .config import get_settings
    from .commons_gallery import collect_commons_candidates
    logs = ImportLog(db, request.get("job_id"))
    settings = get_settings()
    logs.append("공식 출처 수집 시작")
    pages = collect_artist_sources(request.get("official_source_urls", []), logs=logs)
    artist_name = request["artist_name"].strip()
    slug = request.get("existing_artist_slug") or _slug(artist_name)
    scopes = set(request.get("scopes", []))
    aliases = list(dict.fromkeys(filter(None, [artist_name, (request.get("candidate") or {}).get("label"), request.get("existing_artist_slug")])))
    official_youtube_url = request.get("official_youtube_url") or next(
        (url for url in request.get("official_source_urls", [])
         if re.match(r"^https://(?:www\.|m\.)?youtube\.com/(?:@|channel/|c/|user/)", url, re.I)),
        None,
    )
    profile, official_socials, news = profile_and_news(pages, aliases, settings, logs)
    direct_socials = _direct_socials(request.get("official_source_urls", []))
    for platform, field in (("facebook", "facebook_url"), ("x", "x_url"), ("instagram", "instagram_url")):
        if direct_socials.get(field):
            official_socials.setdefault(platform, {"url": direct_socials[field], "evidence_url": direct_socials[field]})
    profile_facts = dict((request.get("candidate") or {}).get("profile_facts") or {})
    profile.update({key: value for key, value in profile_facts.items() if value and not profile.get(key)})
    albums, limited, video_limited, linked = [], False, False, 0
    if scopes & {"albums", "tracks"}:
        albums, pages, limited = crawl_catalog(pages, min(request.get("album_limit", 50), 100), logs)
        if "tracks" in scopes:
            linked, video_limited = connect_youtube(
                albums, pages, settings.youtube_api_key, aliases, logs,
                region=request.get("country_code", "KR"),
                official_youtube_url=official_youtube_url,
                settings=settings,
            )
    writing = draft_artist_sections(request, pages, profile, news, settings, logs)
    gallery_pages = collect_gallery_pages(pages, logs) if scopes & {'gallery', 'profile'} else pages
    commons_limit = min(max(int(request.get('gallery_limit', 40)) // 2, 1), 12)
    commons = collect_commons_candidates((request.get('candidate') or {}).get('id'), commons_limit, logs) if scopes & {'gallery', 'profile'} else []
    gallery_review = classify_gallery(request, gallery_pages, settings, logs, commons) if scopes & {'gallery', 'profile'} else {}
    portrait = representative_photo(gallery_review) if 'profile' in scopes else None
    logs.append('대표 사진 후보 확인 · 관리자 지정 이미지는 유지: ' + portrait['image_url'] if portrait else '대표 사진 미확인 · 임의 배너/로고 사용 안 함, 관리자 선택 필요')
    missing = []
    for scope in ('biography', 'history', 'awards'):
        if scope in scopes and not writing.get(scope, {}).get('entries'):
            missing.append(scope + ' 본문 근거 부족 또는 LLM 작성 실패')
    if "socials" in scopes and not official_socials:
        missing.append("공식 홈페이지에서 SNS 소유 근거 미확인")
    if "albums" in scopes and not albums:
        missing.append("앨범 목록 미확인")
    track_total = sum(len(a['tracks']) for a in albums)
    if "tracks" in scopes and (not track_total or any(not a['tracks'] for a in albums)):
        missing.append("일부 앨범 수록곡 미확인")
    if "tracks" in scopes and linked < track_total:
        missing.append(f"공식 영상 미연결 {track_total-linked}곡")
    if limited or video_limited:
        missing.append("탐색 한도/외부 오류로 추가 확인 필요")
    if "profile" in scopes:
        for field, label in (("debut_text", "데뷔"), ("agency", "소속사"), ("role_description", "활동 분야")):
            if not profile_facts.get(field) and not (field == "debut_text" and profile.get("debut_date")):
                missing.append(label + " 공식 근거 미확인")
    if "gallery" in scopes:
        missing.append("갤러리 원본 검증·서버 저장 보완 필요")
    report = {"quality": "partial" if missing else "complete", "missing": missing,
              "albums_found": len(albums), "tracks_found": track_total, "youtube_linked": linked,
              "sources_checked": len(pages), "checked_at": datetime.now(timezone.utc).isoformat(),
              "profile": profile, "official_socials": official_socials, "news_references": news, "llm_writing": writing, "gallery_review": gallery_review,
              "publication": "review_pending" if request.get("review_before_publish", True) else "published",
              "evidence": [{"title": a['title'], "source_url": a['external_url'], "release_date": a['release_date'], "tracks": a['tracks']} for a in albums]}
    logs.append(f"수집 검증: 앨범 {len(albums)}개 · 곡 {track_total}개 · 공식 영상 {linked}개")
    for reason in missing:
        logs.append("보완 필요: " + reason)
    descriptions = [page["description"] for page in pages if page["description"]]
    socials = {field: official_socials[platform]['url'] for platform, field in
               [('facebook','facebook_url'),('x','x_url'),('instagram','instagram_url')] if platform in official_socials}
    socials = _direct_socials(request.get("official_source_urls", [])) | socials
    fandom_name = _official_fandom_name(pages)
    real_name = profile_facts.get("real_name") or profile_facts.get("official_name")
    active = not request.get("review_before_publish", True)
    values = {
        "slug": slug,
        "name": (request.get("candidate") or {}).get("english_name") or artist_name,
        "name_ko": (request.get("candidate") or {}).get("label") or artist_name,
        "real_name": real_name if "profile" in scopes else None,
        "role_description": profile_facts.get("role_description") if "profile" in scopes else None,
        "debut_text": (profile.get('debut_date') or profile_facts.get("debut_text")) if "profile" in scopes else None,
        "agency": profile_facts.get("agency") if "profile" in scopes else None,
        "fandom_name": fandom_name if "profile" in scopes else None,
        "description": descriptions[0] if descriptions and "biography" in scopes else None,
        "image_url": portrait['image_url'] if portrait else None,
        "hero_image_url": portrait['image_url'] if portrait else None,
        "facebook_url": socials.get("facebook_url") if "socials" in scopes else None,
        "x_url": socials.get("x_url") if "socials" in scopes else None,
        "instagram_url": socials.get("instagram_url") if "socials" in scopes else None,
        "active": active,
    }
    row = db.execute(text("select id,active from public.artists where slug = :slug"), {"slug": slug}).first()
    if row and row.active and request.get("review_before_publish", True):
        report['publication'] = 'review_pending'
        report['missing'].append('기존 공개 데이터 보호 · 새 수집 결과는 근거 보고서에서 검토 필요')
        report['quality'] = 'partial'
        db.rollback()
        _fill_missing_artist_profile(db, row.id, values)
        gallery_count = save_gallery_candidates(db, row.id, gallery_review) if 'gallery' in scopes else 0
        album_count, saved_track_count = _save_artist_albums(db, row.id, albums, scopes, active=False)
        db.commit()
        logs.append('공개 중인 아티스트 정보는 덮어쓰지 않고 새 앨범·곡은 비공개 검토 상태로 저장합니다.')
        logs.append(f'갤러리 확인 후보 {gallery_count}개를 슈퍼 관리자 검토함에 저장했습니다.')
        logs.append(f'앨범 검토 후보 {album_count}개 · 곡 {saved_track_count}개를 저장했습니다.')
        return {"artist_id": row.id, "slug": slug, "sources": len(pages), "gallery": gallery_count,
                "albums": len(albums), "tracks": track_total, "collected": gallery_count + album_count + saved_track_count, "report": report, "logs": list(logs)[-20:]}
    if row:
        artist_id = row.id
        _fill_missing_artist_profile(db, artist_id, values)
        db.execute(text("""
            update public.artists set name_ko=coalesce(name_ko,:name_ko),
              description=coalesce(description,:description),
              image_url=coalesce(nullif(image_url,''),:image_url),
              hero_image_url=coalesce(nullif(hero_image_url,''),:hero_image_url),
              facebook_url=coalesce(facebook_url,:facebook_url), x_url=coalesce(x_url,:x_url),
              instagram_url=coalesce(instagram_url,:instagram_url), updated_at=now()
            where id=:artist_id
        """), values | {"artist_id": artist_id})
    else:
        artist_id = db.execute(text("""
            insert into public.artists
              (slug,name,name_ko,real_name,role_description,debut_text,agency,fandom_name,description,image_url,hero_image_url,facebook_url,x_url,instagram_url,active)
            values (:slug,:name,:name_ko,:real_name,:role_description,:debut_text,:agency,:fandom_name,:description,:image_url,:hero_image_url,:facebook_url,:x_url,:instagram_url,:active)
            returning id
        """), values).scalar_one()
    save_artist_sections(db, artist_id, writing)
    gallery_count = save_gallery_candidates(db, artist_id, gallery_review) if 'gallery' in scopes else 0

    album_count, track_count = _save_artist_albums(db, artist_id, albums, scopes, active)
    db.commit()
    logs.append("검토 데이터 저장 완료")
    return {"artist_id": artist_id, "slug": slug, "sources": len(pages), "gallery": gallery_count, "albums": len(albums), "tracks": track_total,
            "collected": len(albums) + track_total + gallery_count, "report": report, "logs": list(logs)[-20:]}
