"""Bounded official discography crawl and evidence-based YouTube matching.

No arbitrary code from publisher pages is executed. Unsupported layouts and
unmatched recordings remain explicit review gaps, never invented metadata.
"""
import re
import unicodedata
from datetime import date
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import httpx
import feedparser
from bs4 import BeautifulSoup


def canonical_url(url):
    p = urlparse(url)
    return p._replace(fragment="", query=urlencode(sorted((k, v) for k, v in parse_qsl(p.query)
        if k.lower() not in {"ima", "utm_source", "utm_medium", "utm_campaign"}))).geturl()


def key(value):
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", value).casefold())


def youtube_id(url):
    p = urlparse(url)
    host = (p.hostname or "").removeprefix("www.")
    value = None
    if host == "youtu.be":
        value = p.path.strip("/")
    elif host in {"youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        value = dict(parse_qsl(p.query)).get("v")
        if not value and p.path.startswith(("/embed/", "/shorts/")):
            value = p.path.split("/")[2]
    return value if value and re.fullmatch(r"[A-Za-z0-9_-]{11}", value) else None


def release_date(value):
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def html_album(page):
    """Official Japanese fanclub CMS adapter (also used by other artists)."""
    soup = BeautifulSoup(page.get("html", ""), "html.parser")
    detail = soup.select_one("#page_discography .entry_detail")
    if not detail:
        return None
    heading = detail.select_one(".title_area h3")
    if not heading:
        return None
    album_type = heading.select_one("span")
    album_type = album_type.get_text(" ", strip=True) if album_type else ""
    for span in heading.select("span"):
        span.decompose()
    title = heading.get_text(" ", strip=True)
    if not title:
        return None
    tracks = []
    nodes = detail.select(".tracklist ol li, .track_list ol li")
    if nodes:
        titles = [n.get_text(" ", strip=True) for n in nodes]
    else:
        # Some releases use numbered lines rather than list markup.
        area = detail.select_one(".tracklist, .track_list, .elements")
        titles = []
        for line in (area.get_text("\n", strip=True).splitlines() if area else []):
            m = re.match(r"^(?:M\s*)?\d{1,2}[.．、)\s]+(.+)$", line)
            if m:
                titles.append(m.group(1))
    for title_text in titles[:200]:
        title_text = re.sub(r"^\d{1,2}[.．、)\s]+", "", title_text).strip()
        if title_text:
            tracks.append({"title": title_text[:300], "duration": None, "url": None,
                           "source_url": page["url"]})
    image = detail.select_one(".discography_jkt img")
    return {"title": title[:200], "album_type": album_type,
            "release_date": release_date(detail.get_text(" ", strip=True)),
            "cover_url": urljoin(page["url"], image.get("src", "")) if image else None,
            "external_url": canonical_url(page["url"]), "tracks": tracks}


def profile_and_news(pages, aliases, settings, logs):
    from .artist_import import _collect_artist_source, _public_https_url
    profile, news, socials = {}, [], {}
    targets = []
    platforms = {'youtube.com': 'youtube', 'instagram.com': 'instagram', 'tiktok.com': 'tiktok',
                 'facebook.com': 'facebook', 'x.com': 'x', 'twitter.com': 'x'}
    for page in pages:
        host = (urlparse(page['url']).hostname or '').removeprefix('www.')
        if host in platforms:
            continue
        for link in page['links']:
            target = urlparse(link)
            domain = (target.hostname or '').removeprefix('www.')
            if domain in platforms:
                socials.setdefault(platforms[domain], {'url': link, 'evidence_url': page['url']})
            if target.hostname == urlparse(page['url']).hostname and re.search(r'profile|biography|/about', link, re.I):
                if canonical_url(link) not in targets:
                    targets.append(canonical_url(link))
    for url in targets[:4]:
        logs.append(f'공식 프로필 확인: {url}')
        try:
            for page in _collect_artist_source(url, 15, logs):
                soup = BeautifulSoup(page.get('html', ''), 'html.parser')
                section = soup.select_one('#profile_detail .read_area')
                if section:
                    paragraphs = [p.get_text(' ', strip=True) for p in section.select('p')]
                    profile.update(source_url=url, paragraphs_original=paragraphs,
                                   source_language=soup.html.get('lang') if soup.html else None)
                    text_value = ' '.join(paragraphs)
                    m = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日デビュー', text_value)
                    if m:
                        try:
                            profile['debut_date'] = date(*map(int, m.groups())).isoformat()
                        except ValueError:
                            pass
                    logs.append('공식 소개 원문·데뷔 정보 확보 · 번역/검토 별도')
        except (httpx.HTTPError, OSError, ValueError):
            logs.append(f'프로필 접근 실패 · 재확인 필요: {url}')
    # News is corroborating evidence, not authority to overwrite a profile or
    # promote a channel. Only administrator-configured feeds/API are used.
    def relevant(title):
        return any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', title, re.I) for a in aliases if a)
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        for url in settings.rss_feeds[:10]:
            try:
                _public_https_url(url)
                response = client.get(url)
                response.raise_for_status()
                for entry in feedparser.parse(response.content).entries[:100]:
                    title = str(entry.get('title', ''))
                    link = str(entry.get('link', ''))
                    if relevant(title) and urlparse(link).scheme == 'https':
                        news.append({'title': title[:300], 'url': link, 'published': entry.get('published'), 'feed': url})
            except (httpx.HTTPError, OSError, ValueError):
                logs.append(f'뉴스 피드 확인 실패: {url}')
        if settings.news_api_key:
            try:
                response = client.get('https://newsapi.org/v2/everything', params={'q': aliases[0], 'pageSize': 30},
                                      headers={'X-Api-Key': settings.news_api_key})
                if response.is_success:
                    for entry in response.json().get('articles', []):
                        if relevant(entry.get('title') or '') and urlparse(entry.get('url') or '').scheme == 'https':
                            news.append({'title': entry['title'], 'url': entry['url'], 'published': entry.get('publishedAt')})
                else:
                    logs.append(f'뉴스 API HTTP {response.status_code} · 교차 확인 보류')
            except httpx.HTTPError:
                logs.append('뉴스 API 연결 실패 · 교차 확인 보류')
    news = list({item['url']: item for item in news}.values())[:30]
    logs.append(f'뉴스 교차 확인 후보 {len(news)}건 · 기사 제목만으로 사실 확정하지 않음')
    for item in news:
        logs.append(f"뉴스 근거 후보: {item['title']} · {item['url']}")
    return profile, socials, news


def crawl_catalog(pages, limit, logs, max_pages=80):
    from .artist_import import _collect_artist_source, _music_albums
    albums, seen_albums, visited = [], set(), set()
    queue = []
    roots = {urlparse(p["url"]).hostname for p in pages
             if not any(s in (urlparse(p["url"]).hostname or "") for s in ("youtube.", "instagram.", "tiktok.", "facebook.", "x.com", "twitter."))}
    all_pages = list(pages)
    def consume(page):
        parsed = _music_albums([page], limit)
        extra = html_album(page)
        if extra:
            parsed.append(extra)
        for album in parsed:
            identity = (key(album["title"]), album.get("release_date"))
            if identity in seen_albums:
                continue
            seen_albums.add(identity)
            albums.append(album)
            logs.append(f"앨범 확인: {album['title']} · 수록곡 {len(album['tracks'])}개 · {page['url']}")
        for link in page["links"]:
            url = canonical_url(link)
            if urlparse(url).hostname not in roots:
                continue
            if re.search(r"discograph|diarKijiShw|/albums?[/?.]|/releases?[/?.]", url, re.I):
                if url not in visited and url not in queue:
                    queue.append(url)
    for page in pages:
        visited.add(canonical_url(page["url"]))
        consume(page)
    fetched = 0
    while queue and fetched < max_pages and len(albums) < limit:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        fetched += 1
        logs.append(f"공식 앨범 페이지 탐색: {url}")
        try:
            children = _collect_artist_source(url, 15, logs)
            for page in children:
                all_pages.append(page)
                consume(page)
        except (httpx.HTTPError, OSError, ValueError):
            logs.append(f"앨범 페이지 접근 실패 · 재확인 필요: {url}")
    limited = bool(queue) or len(albums) > limit
    if limited:
        logs.append("앨범 탐색 한도 도달 · 전체 목록 확인 필요")
    return albums[:limit], all_pages, limited


def recording_title(title):
    """Drop CMS footnotes, not recording-version suffixes such as Japanese ver."""
    return re.split(r"[※＊]", title, maxsplit=1)[0].strip()


def video_match(track_title, video, aliases, region="KR"):
    track_title = recording_title(track_title)
    snippet = video.get("snippet", {})
    title = snippet.get("title", "")
    lower = title.casefold()
    status = video.get("status", {})
    content = video.get("contentDetails", {})
    restrictions = content.get("regionRestriction", {})
    if status.get("privacyStatus") != "public" or not status.get("embeddable"):
        return 0
    if region in restrictions.get("blocked", []) or ("allowed" in restrictions and region not in restrictions["allowed"]):
        return 0
    if re.search(r"\b(?:teaser|trailer|preview|shorts|reaction|behind|challenge|making|fancam|live|performance|cover)\b|dance practice|티저|직캠|챌린지|비하인드", lower):
        return 0
    # Versions must agree; a Japanese, instrumental or remix recording must
    # never silently replace the original recording.
    for pattern in (r"japanese|일본|日本", r"english|영어", r"remix", r"instrumental|inst\.", r"acoustic"):
        if bool(re.search(pattern, track_title, re.I)) != bool(re.search(pattern, title, re.I)):
            return 0
    variants = [track_title]
    variants += re.findall(r"\(([^)]+)\)", track_title)
    variants.append(re.sub(r"\([^)]*\)", "", track_title).strip())
    quoted = re.findall(r"['\"‘’“”]([^'\"‘’“”]+)['\"‘’“”]", title)
    cleaned = title
    for alias in sorted(aliases, key=len, reverse=True):
        cleaned = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"official|music video|m/v|\bmv\b|audio|visualizer|lyric video", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[\[\]()'\"‘’“”_-]", " ", cleaned)
    candidates = [cleaned, *quoted]
    exact = any(key(v) == key(c) for v in variants if len(key(v)) >= 2 for c in candidates)
    if not exact:
        return 0
    artist_context = title + " " + snippet.get("description", "")[:1500]
    if not any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", artist_context, re.I) for a in aliases if a):
        return 0
    if not re.search(r"official|\bmv\b|m/v|music video|provided to youtube", lower + " " + snippet.get("description", "")[:500].casefold()):
        return 0
    return 100 if re.search(r"\bmv\b|m/v|music video", lower) else 90


def connect_youtube(albums, pages, api_key, aliases, logs, region="KR", search_budget=30):
    """Search only channels evidenced by official-site outbound links/videos.

    The search budget is per execution and explicitly surfaced, not unlimited.
    Unverified global search matches are never auto-attached.
    """
    if not api_key:
        logs.append("YouTube API 설정 없음 · 공식 영상 연결 보류")
        return 0, True
    links = [link for p in pages if not any(s in (urlparse(p['url']).hostname or '')
             for s in ('youtube.', 'instagram.', 'tiktok.', 'facebook.', 'x.com', 'twitter.')) for link in p['links']]
    channel_ids = set()
    video_ids = list(dict.fromkeys(filter(None, (youtube_id(u) for u in links))))[:50]
    for link in links:
        p = urlparse(link)
        if (p.hostname or '').removeprefix('www.') == 'youtube.com' and re.fullmatch(r'/channel/UC[\w-]{22}/?', p.path):
            channel_ids.add(p.path.split('/')[2])
    cache, calls, linked, limited = {}, 0, 0, False
    search_disabled = False
    with httpx.Client(timeout=20) as client:
        def api(resource, **params):
            response = client.get(f"https://www.googleapis.com/youtube/v3/{resource}", params=params | {"key": api_key})
            if response.is_error:
                # Never expose a request URL containing the API key in logs.
                raise ValueError(f"YouTube API HTTP {response.status_code} · 할당량/접근 설정 확인 필요")
            return response.json().get('items', [])
        try:
            direct = api('videos', part='snippet,status,contentDetails', id=','.join(video_ids)) if video_ids else []
            for video in direct:
                channel_ids.add(video['snippet']['channelId'])
            for link in links:
                p = urlparse(link)
                if (p.hostname or '').removeprefix('www.') == 'youtube.com' and p.path.startswith('/@'):
                    for channel in api('channels', part='id', forHandle=p.path.strip('/')):
                        channel_ids.add(channel['id'])
            if not channel_ids:
                logs.append("공식 홈페이지에서 채널 소유 근거를 확보하지 못함 · 영상 연결 검토 필요")
                return 0, True
            logs.append(f"공식 홈페이지의 채널/영상 링크로 YouTube 채널 {len(channel_ids)}개 확인")
            # Read uploads in batches instead of spending a search call on
            # every recording. Retain the explicit cap for very large labels.
            for channel in sorted(channel_ids):
                channels = api('channels', part='contentDetails', id=channel)
                uploads = channels[0].get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads') if channels else None
                token = None
                if not uploads:
                    continue
                for page_number in range(20):
                    params = {'part': 'contentDetails', 'playlistId': uploads, 'maxResults': 50, 'key': api_key}
                    if token:
                        params['pageToken'] = token
                    response = client.get('https://www.googleapis.com/youtube/v3/playlistItems', params=params)
                    if response.is_error:
                        raise ValueError(f'YouTube 업로드 목록 HTTP {response.status_code}')
                    data = response.json()
                    ids = [i['contentDetails']['videoId'] for i in data.get('items', []) if i.get('contentDetails', {}).get('videoId')]
                    if ids:
                        direct.extend(api('videos', part='snippet,status,contentDetails', id=','.join(ids)))
                    logs.append(f'공식 채널 영상 목록 확인: {channel} · {page_number+1}페이지')
                    token = data.get('nextPageToken')
                    if not token:
                        break
                if token:
                    limited = True
            for album in albums:
                for track in album['tracks']:
                    identity = key(track['title'])
                    if identity not in cache:
                        candidates = list(direct)
                        for channel in sorted(channel_ids):
                            if any(video_match(track['title'], v, aliases, region) for v in candidates):
                                break
                            if search_disabled or calls >= search_budget:
                                limited = True
                                break
                            calls += 1
                            logs.append(f"공식 YouTube 검색: {track['title']} · 채널 {channel}")
                            try:
                                hits = api('search', part='snippet', type='video', channelId=channel,
                                    q=f"{aliases[0]} {recording_title(track['title'])}", maxResults=5, videoEmbeddable='true', regionCode=region)
                                ids = [h['id']['videoId'] for h in hits if h.get('id', {}).get('videoId')]
                                if ids:
                                    candidates.extend(api('videos', part='snippet,status,contentDetails', id=','.join(ids)))
                            except (httpx.HTTPError, ValueError) as exc:
                                limited = search_disabled = True
                                logs.append((str(exc) if isinstance(exc, ValueError) else 'YouTube 검색 요청 실패') + ' · 추가 검색 중지, 확보된 공식 영상으로 나머지 곡 연결 계속')
                                break
                        ranked = sorted(((video_match(track['title'], v, aliases, region), v) for v in candidates), key=lambda x: x[0], reverse=True)
                        cache[identity] = ranked[0][1] if ranked and ranked[0][0] else None
                    best = cache[identity]
                    if best:
                        track['url'] = f"https://www.youtube.com/watch?v={best['id']}"
                        track['video_evidence'] = {'channel_id': best['snippet']['channelId'], 'title': best['snippet']['title'], 'source': 'official_site_link'}
                        track['video_duration'] = best.get('contentDetails', {}).get('duration')
                        linked += 1
                        logs.append(f"곡·공식 영상 연결: {track['title']} · {track['url']}")
                    else:
                        logs.append(f"공식 영상 미확인: {track['title']} · 곡 정보는 유지")
        except (httpx.HTTPError, ValueError) as exc:
            logs.append(str(exc) if isinstance(exc, ValueError) else 'YouTube 연결 실패 · 곡 정보는 유지')
            limited = True
    if limited:
        logs.append("YouTube 검색 한도 또는 외부 오류 · 미연결 곡 재확인 필요")
    return linked, limited
