import pytest
from types import SimpleNamespace
from media_collector import artist_catalog
from media_collector.artist_catalog import canonical_url, html_album, video_match, youtube_id, crawl_catalog
from media_collector import artist_import


def test_album_detail_extracts_all_ordered_tracks_and_date():
    page = {'url': 'https://official.example/detail?id=1', 'html': '''
    <section id="page_discography"><div class="entry_detail">
    <div class="title_area"><h3><span>1st ALBUM</span>I've IVE</h3><p>2023.4.10 RELEASE</p></div>
    <div class="discography_jkt"><img src="/cover.jpg"></div>
    <div class="tracklist"><ol><li>Blue Blood</li><li>I AM</li><li>섬찟(Hypnosis)</li></ol></div>
    </div></section>'''}
    album = html_album(page)
    assert album['title'] == "I've IVE"
    assert album['release_date'] == '2023-04-10'
    assert [t['title'] for t in album['tracks']] == ['Blue Blood', 'I AM', '섬찟(Hypnosis)']
    assert album['cover_url'] == 'https://official.example/cover.jpg'


def test_canonical_url_keeps_pagination_but_drops_clock_and_fragment():
    assert canonical_url('https://official.example/list?ima=123&page=2#top') == 'https://official.example/list?page=2'


def video(title, **kwargs):
    return {'snippet': {'title': title, 'description': 'IVE Official Music'},
            'status': {'privacyStatus': 'public', 'embeddable': True},
            'contentDetails': {}, **kwargs}


def test_official_mv_matches_exact_song():
    assert video_match('I AM', video("IVE 아이브 'I AM' MV"), ['IVE', '아이브']) == 100
    assert video_match('섬찟(Hypnosis)', video('Hypnosis', snippet={'title': 'Hypnosis', 'description': 'Provided to YouTube IVE'}), ['IVE']) == 90


def test_exact_song_from_explicit_official_channel_does_not_require_title_alias():
    official_upload = video('Glitch', snippet={'title': 'Glitch', 'description': '', 'channelId': 'UCofficial'})
    assert video_match('Glitch', official_upload, ['권은비'], trusted_channel=True) == 90
    assert video_match('Glitch', official_upload, ['권은비']) == 0


@pytest.mark.parametrize('title', ["IVE 'I AM' MV Teaser", "IVE 'I AM' LIVE", "IVE 'I AM' Japanese ver. Official MV", "IVE 'I AM' dance practice", "IVE 'I AM' performance", "IVE 'I AM NOT' MV", "IVE 'I AM' Instrumental", "IVE 'I AM' cover"])
def test_wrong_versions_and_non_recordings_do_not_match(title):
    assert video_match('I AM', video(title), ['IVE']) == 0


def test_private_blocked_and_unembeddable_do_not_match():
    assert video_match('I AM', video("IVE 'I AM' MV", status={'privacyStatus': 'private', 'embeddable': True}), ['IVE']) == 0
    assert video_match('I AM', video("IVE 'I AM' MV", contentDetails={'regionRestriction': {'blocked': ['KR']}}), ['IVE']) == 0
    assert video_match('I AM', video("IVE 'I AM' MV", status={'privacyStatus': 'public', 'embeddable': False}), ['IVE']) == 0


def test_cms_footnotes_are_not_recording_versions():
    assert video_match('LUCID DREAM ※日本オリジナル', video("IVE 'LUCID DREAM' Official MV"), ['IVE']) == 100
    assert video_match('Fashion ※日本オリジナル※ App Store', video("IVE 'Fashion' Official MV"), ['IVE']) == 100
    assert video_match('ALIVE', video("IVE 'ALIVE' Official MV"), ['IVE']) == 100
    assert video_match('REBEL HEART -Japanese ver.-', video("IVE 'REBEL HEART' Official MV"), ['IVE']) == 0


def test_search_rate_limit_does_not_discard_known_official_videos(monkeypatch):
    import httpx
    from media_collector import artist_catalog
    known = video("IVE 'I AM' MV")
    known['id'] = '12345678901'
    known['snippet']['channelId'] = 'UC' + 'a' * 22
    def respond(request):
        endpoint = request.url.path.rsplit('/', 1)[-1]
        if endpoint == 'search': return httpx.Response(429, json={})
        if endpoint == 'videos': return httpx.Response(200, json={'items': [known]})
        return httpx.Response(200, json={'items': []})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(artist_catalog.httpx, 'Client', lambda **kw: client)
    tracks = [{'title': 'Missing'}, {'title': 'I AM'}]
    logs = []
    result = artist_catalog.connect_youtube([{'tracks': tracks}], [{'url': 'https://official.example', 'links': ['https://youtu.be/12345678901']}], 'test', ['IVE'], logs)
    assert result == (1, True)
    assert tracks[1]['url'] == 'https://www.youtube.com/watch?v=12345678901'
    assert any('429' in log for log in logs)


def test_non_youtube_track_url_is_not_a_video():
    assert youtube_id('https://untrusted.example/watch?v=12345678901') is None
    assert youtube_id('https://youtu.be/12345678901') == '12345678901'


def test_explicit_official_youtube_channel_is_used_without_homepage_link(monkeypatch):
    requested = []

    class Response:
        is_error = False

        def json(self):
            return {"items": []}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def get(self, url, params=None):
            requested.append((url, params or {}))
            if url.endswith('/channels') and (params or {}).get('forHandle'):
                return type('HandleResponse', (), {'is_error': False, 'json': lambda self: {'items': [{'id': 'UC123'}]}})()
            return Response()

    monkeypatch.setattr(artist_catalog.httpx, 'Client', Client)
    logs = []
    artist_catalog.connect_youtube([], [], 'key', ['아이유'], logs, official_youtube_url='https://www.youtube.com/@dlwlrma')
    assert any(params.get('forHandle') == '@dlwlrma' for _, params in requested)
    assert any('직접 지정한 공식 채널' in message for message in logs)


def test_official_youtube_description_creates_review_release_candidate():
    video_item = {
        'id': 'abcdefghijk',
        'snippet': {
            'channelId': 'UCofficial',
            'title': "권은비(KWON EUNBI) 'Hello Stranger' M/V",
            'description': 'KWON EUNBI 3rd Digital Single [Hello Stranger] : M/V',
            'publishedAt': '2025-04-15T09:00:00Z',
            'thumbnails': {'high': {'url': 'https://i.ytimg.com/cover.jpg'}},
        },
        'contentDetails': {'duration': 'PT3M22S'},
    }
    settings = SimpleNamespace(
        naver_client_id=None,
        naver_client_secret=None,
        naver_api_provider='developers',
        request_timeout_seconds=10,
    )
    logs = []

    albums = artist_catalog.youtube_release_candidates(
        [video_item], {'UCofficial'}, ['권은비', 'KWON EUNBI'], settings, logs
    )

    assert albums[0]['title'] == 'Hello Stranger'
    assert albums[0]['album_type'].lower() == 'digital single'
    assert albums[0]['release_date'] is None
    assert albums[0]['tracks'][0]['title'] == 'Hello Stranger'
    assert albums[0]['tracks'][0]['url'].endswith('abcdefghijk')
    assert albums[0]['tracks'][0]['release_evidence'] is None


def test_crawler_follows_same_site_discography_and_reports_limit(monkeypatch):
    fetched = []
    def fetch(url, timeout, logs):
        fetched.append(url)
        return [{'url': url, 'html': '', 'json_ld': [], 'links': ['https://official.example/discography?page=2']}]
    monkeypatch.setattr(artist_import, '_collect_artist_source', fetch)
    initial = [{'url': 'https://official.example', 'html': '', 'json_ld': [], 'links': ['https://official.example/discography?ima=1', 'https://other.example/albums/']}]
    albums, pages, limited = crawl_catalog(initial, 50, [], max_pages=1)
    assert fetched == ['https://official.example/discography']
    assert limited
