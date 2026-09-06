from types import SimpleNamespace
from pathlib import Path
import json
import subprocess

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from media_collector import admin, main
from media_collector.artist_import import ArtistPageParser, _commons_source_url, _slug
from media_collector.models import Base, CollectionJob, CollectionRule, CollectorSettings
from media_collector.presets import DEFAULT_NEWS_SOURCES


def test_collector_settings_seeds_domestic_official_news_feeds():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        result = admin.collector_settings(session)

        assert result["news_sources"] == DEFAULT_NEWS_SOURCES
        assert session.get(CollectorSettings, True).news_sources == DEFAULT_NEWS_SOURCES
        names = {source["name"] for source in result["news_sources"]}
        assert {"뉴시스 연예", "매일경제 문화·연예", "MBN 연예", "연합뉴스 연예", "스타뉴스"} <= names
        assert {"뉴스엔", "OSEN", "SPOTV NEWS", "텐아시아", "엑스포츠뉴스", "MBC연예"} <= names


def test_collection_timing_renders_actual_times_and_partial_status():
    script = admin.ARTIST_IMPORT_HTML
    function = script.split('function renderCollectionTiming(job){', 1)[1].split('\nrenderCollectionTiming(null);', 1)[0]
    checks = '''
const timing={dataset:{},innerHTML:''},esc=v=>String(v);
const completionDetails={hidden:true,innerHTML:'',open:true};let completionSignature='';
''' + 'function renderCollectionTiming(job){' + function + '''
renderCollectionTiming({status:'completed',started_at:'2026-09-06T01:00:00Z',completed_at:'2026-09-06T01:01:00Z',report:{quality:'partial'}});
if(!timing.innerHTML.includes('일부 수집 완료')||timing.innerHTML.includes('—'))throw Error('completed timestamps missing');
renderCollectionTiming({status:'pending'});
if(!timing.innerHTML.includes('수집 대기')||!timing.innerHTML.includes('수집 시작: —'))throw Error('invented start time');
renderCollectionTiming({status:'failed',completed_at:'2026-09-06T01:01:00Z'});
if(timing.dataset.state!=='failed'||!timing.innerHTML.includes('수집 실패'))throw Error('failure missing');
renderCollectionTiming(null);
if(!timing.innerHTML.includes('수집 전'))throw Error('new artist state missing');
renderCollectionTiming({job_id:'1',status:'completed',report:{quality:'partial'},completion_issues:[{title:'보완',detail:'원본 저장 미지원',action:'검토하세요'}]});
if(completionDetails.hidden||!completionDetails.innerHTML.includes('원본 저장 미지원')||!completionDetails.innerHTML.includes('검토하세요'))throw Error('details missing');
if(!completionDetails.open)throw Error('poll closed details');
renderCollectionTiming({status:'pending'});
if(!completionDetails.hidden)throw Error('old issues remain');
'''
    subprocess.run(['node', '-e', checks], check=True, capture_output=True, text=True)


def test_artist_import_page_exposes_header_entry_and_all_content_scopes():
    assert 'href="/admin/artists">아티스트 정보 가져오기</a>' in admin.ADMIN_HTML
    assert "아티스트 정보 가져오기" in admin.ARTIST_IMPORT_HTML
    for scope in ("profile", "socials", "biography", "history", "awards", "albums", "tracks", "gallery"):
        assert f'value="{scope}"' in admin.ARTIST_IMPORT_HTML
    assert 'id="job-search"' in admin.ARTIST_IMPORT_HTML
    assert 'id="job-status"' in admin.ARTIST_IMPORT_HTML
    assert 'id="job-sort"' in admin.ARTIST_IMPORT_HTML
    assert 'id="discover-artist-sources"' in admin.ARTIST_IMPORT_HTML
    assert 'id="source-discovery-status"' in admin.ARTIST_IMPORT_HTML
    assert "chooseArtist(preview.candidates||[],'sources')" in admin.ARTIST_IMPORT_HTML
    assert 'Wikimedia Commons는 이미지 검증 출처로 항상 포함됩니다.' in admin.ARTIST_IMPORT_HTML
    assert ".jobs-panel{border-color:#566178" in admin.ARTIST_IMPORT_HTML
    assert ".settings-panel{grid-column:1;grid-row:1}" in admin.ARTIST_IMPORT_HTML
    assert ".scope-panel{grid-column:1;grid-row:2}" in admin.ARTIST_IMPORT_HTML
    assert 'id="artist-pane-divider" class="pane-divider"' in admin.ARTIST_IMPORT_HTML
    assert 'id="run-import-top"' in admin.ARTIST_IMPORT_HTML
    assert 'id="run-import-top" class="hero-run" type="button">수집 실행</button>' in admin.ARTIST_IMPORT_HTML
    assert 'id="run-status" class="hero-run-status"' in admin.ARTIST_IMPORT_HTML
    assert "importForm.requestSubmit()" in admin.ARTIST_IMPORT_HTML
    assert '.pane-divider::after{content:"⋮"' in admin.ARTIST_IMPORT_HTML
    assert '<section class="left-pane"><div class="pane-tabbar">' in admin.ARTIST_IMPORT_HTML
    assert 'data-refresh-schedule=' in admin.ARTIST_IMPORT_HTML
    assert 'data-refresh-now=' in admin.ARTIST_IMPORT_HTML
    assert ".left-pane{grid-column:1;grid-row:1;min-width:0;padding:0 30px 0 0;border:0;border-radius:0;background:transparent" in admin.ARTIST_IMPORT_HTML
    assert '.pane-divider{display:block!important' in admin.ARTIST_IMPORT_HTML
    assert '.pane-divider::before{content:"";position:absolute;inset:0 auto 0 9px;width:2px;background:#f4f5f8' in admin.ARTIST_IMPORT_HTML
    assert ".jobs-panel{position:sticky;grid-column:3;grid-row:1" in admin.ARTIST_IMPORT_HTML
    assert 'id="activity-log-body"' in admin.ARTIST_IMPORT_HTML
    assert '<span class="pane-tab">수집 편집기</span>' in admin.ARTIST_IMPORT_HTML
    assert '<span class="pane-tab">아티스트 탐색기</span>' in admin.ARTIST_IMPORT_HTML
    assert '.layout{height:100%;grid-template-columns:' in admin.ARTIST_IMPORT_HTML
    assert '.activity-log{display:flex;flex-direction:column;height:270px' in admin.ARTIST_IMPORT_HTML
    assert '/admin/api/artist-imports/activity?limit=50' in admin.ARTIST_IMPORT_HTML
    assert "confirm(`${attention.artist_name}의 공식 채널" in admin.ARTIST_IMPORT_HTML


def test_artist_list_uses_admin_summary_filters_and_responsive_cards():
    page = admin.ARTIST_IMPORT_HTML
    assert 'class="section-eyebrow">ARTIST MANAGEMENT</span>' in page
    assert "className='artist-overview'" in page
    assert "setAttribute('aria-label','아티스트 수집 현황')" in page
    assert 'className=\'artist-card-avatar\'' in page
    assert 'className=\'artist-card-action\'' in page
    assert 'body.artist-list-page .jobs{display:grid;grid-template-columns:repeat(3' in page
    assert '@media(max-width:700px)' in page
    assert '<span>아티스트 검색</span><input id="job-search"' in page
    assert '<span>수집 상태</span><select id="job-status"' in page
    assert '<span>목록 정렬</span><select id="job-sort"' in page
    assert 'body.artist-list-page .pane-tabbar{display:none}' in page
    assert "actions.className='jobs-head-actions'" in page
    assert "actions.append(refresh,nav)" in page
    assert 'class="toolbar-heading"' in page
    assert 'class="metric-value"' in page


def test_artist_detail_exposes_collection_editor_and_results_tabs():
    page = admin.ARTIST_IMPORT_HTML
    assert "setAttribute('aria-label','아티스트 수집 상세')" in page
    assert 'data-detail-tab="editor">수집 편집기' in page
    assert 'data-detail-tab="result" tabindex="-1">수집 결과' in page
    assert "resultPane.id='artist-result-pane'" in page
    assert '항목별 수집 현황' in page
    assert '수집된 내용과 근거' in page
    assert '보완이 필요한 항목' in page
    assert "renderArtistResult(job)" in page
    assert "activityLog.hidden=!result" in page
    for label in ("프로필", "공식 SNS", "소개", "연혁", "수상", "앨범", "수록곡", "갤러리"):
        assert label in page


def test_artist_import_n8n_workflow_is_versioned_and_active():
    path = Path(__file__).parents[3] / "automation/n8n/fanheat-artist-profile-import.json"
    workflow = json.loads(path.read_text())
    assert workflow["name"] == "FANHEAT artist profile import"
    assert workflow["active"] is True
    assert {node["name"] for node in workflow["nodes"]} >= {
        "Artist Import Webhook",
        "Discover Official Channels",
        "Official Source Confirmed",
        "Request Source Confirmation",
        "Collect Official Artist Data",
        "Complete Artist Import",
        "Fail Artist Import",
    }
    assert "artist_id" in next(
        node["parameters"]["jsonBody"] for node in workflow["nodes"] if node["name"] == "Complete Artist Import"
    )

    refresh_path = Path(__file__).parents[3] / "automation/n8n/fanheat-artist-scheduled-refresh.json"
    refresh_workflow = json.loads(refresh_path.read_text())
    assert refresh_workflow["name"] == "FANHEAT scheduled artist refresh"
    assert refresh_workflow["active"] is True
    assert {node["name"] for node in refresh_workflow["nodes"]} >= {
        "Artist Refresh Schedule", "Claim Due Artists", "Refresh Official Artist Data", "Complete Artist Refresh"
    }


def test_artist_page_parser_extracts_official_metadata_and_structured_album():
    parser = ArtistPageParser("https://artist.example/profile")
    parser.feed("""
      <html><head><title>Artist Official</title>
      <meta property="og:description" content="Official biography">
      <meta property="og:image" content="/profile.jpg">
      <script type="application/ld+json">{"@type":"MusicAlbum","name":"First Album"}</script>
      </head><body><a href="https://instagram.com/artist">Instagram</a></body></html>
    """)
    assert parser.title == "Artist Official"
    assert parser.meta["og:description"] == "Official biography"
    assert parser.json_ld[0]["name"] == "First Album"
    assert parser.links == ["https://instagram.com/artist"]
    assert _slug("BLACKPINK") == "blackpink"


def test_artist_import_request_requires_a_scope_and_valid_official_urls():
    with pytest.raises(ValidationError):
        admin.AdminArtistImportRequest(artist_name="아이유", scopes=[])
    with pytest.raises(ValidationError):
        admin.AdminArtistImportRequest(
            artist_name="아이유",
            scopes=["profile"],
            official_source_urls=["javascript:alert(1)"],
        )
    with pytest.raises(ValidationError):
        admin.AdminArtistImportRequest(
            artist_name="아이유",
            scopes=["profile"],
            official_source_urls=["https://127.0.0.1/private"],
        )


def test_commons_source_prefers_category_and_has_artist_search_fallback():
    category_entity = {"claims": {"P373": [{"mainsnak": {"datavalue": {"value": "IVE (group)"}}}]}}
    assert _commons_source_url(category_entity, "아이브") == "https://commons.wikimedia.org/wiki/Category:IVE_(group)"
    assert _commons_source_url({}, "아이브") == "https://commons.wikimedia.org/wiki/Special:MediaSearch?type=image&search=%EC%95%84%EC%9D%B4%EB%B8%8C"


def test_artist_discovery_uses_name_when_urls_are_empty(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(youtube_api_key="youtube-key", request_timeout_seconds=12),
    )
    calls = []

    def fake_discovery(artist_name, **kwargs):
        calls.append((artist_name, kwargs))
        return {
            "official_source_urls": ["https://www.youtube.com/channel/official"],
            "can_collect": True,
            "ambiguous": False,
            "confidence": 0.94,
            "logs": ["YouTube 공식 채널 후보 확인"],
        }

    monkeypatch.setattr(main, "discover_artist_sources", fake_discovery)
    result = main.discover_artist_channels(
        {"artist_name": "아이유", "official_source_urls": [], "country_code": "KR", "language_code": "ko"}
    )

    assert calls[0][0] == "아이유"
    assert calls[0][1]["youtube_api_key"] == "youtube-key"
    assert result["can_collect"] is True
    assert result["official_source_urls"] == ["https://www.youtube.com/channel/official"]


def test_artist_import_creates_job_and_calls_server_side_n8n_webhook(monkeypatch):
    settings = SimpleNamespace(
        n8n_artist_webhook_url="http://n8n.test/webhook/fanheat-artist-import",
        internal_api_key="internal-secret",
    )
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    calls = []

    class StubResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return StubResponse()

    monkeypatch.setattr(admin.httpx, "post", fake_post)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = admin.AdminArtistImportRequest(
        artist_name="아이유",
        existing_artist_slug="iu",
        official_source_urls=["https://www.youtube.com/@dlwlrma"],
        scopes=["profile", "albums", "tracks", "gallery"],
    )
    request.identity_confirmation = admin._sign_identity(request, {
        "id": "Q123", "label": "아이유", "english_name": "IU",
        "description": "가수", "entity_url": "https://www.wikidata.org/wiki/Q123",
        "commons_source_url": "https://commons.wikimedia.org/wiki/Category:IU",
        "official_source_urls": ["https://www.youtube.com/@dlwlrma"],
    })

    with Session(engine, expire_on_commit=False) as session:
        result = admin.start_artist_import(request, session)
        job = session.scalar(select(CollectionJob).where(CollectionJob.source == "artist"))

    assert result["job_id"] == job.id
    assert job.query == "아이유"
    assert job.status == "pending"
    assert calls
    sent = calls[0][1]["json"]
    assert sent["job_id"] == job.id
    assert sent["existing_artist_slug"] == "iu"
    assert sent["candidate"]["id"] == "Q123"
    assert sent["candidate"]["commons_source_url"] == "https://commons.wikimedia.org/wiki/Category:IU"
    assert sent["official_source_urls"] == [
        "https://www.youtube.com/@dlwlrma",
        "https://commons.wikimedia.org/wiki/Category:IU",
    ]
    assert "identity_confirmation" not in sent
    assert sent["scopes"] == ["profile", "albums", "tracks", "gallery"]
    assert calls[0][1]["headers"]["X-FANHEAT-AUTOMATION-KEY"] == "internal-secret"


@pytest.mark.parametrize("count", [0, 1, 3])
def test_candidate_preview_never_starts_collection(monkeypatch, count):
    from media_collector import artist_import
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="secret"))
    candidates = [{"id": f"Q{i+1}", "label": "동명이인", "official_source_urls": [f"https://example.com/{i}"]} for i in range(count)]
    monkeypatch.setattr(artist_import, "search_artist_candidates", lambda *args: candidates)
    monkeypatch.setattr(admin, "_create_artist_job", lambda *args, **kwargs: pytest.fail("preview created job"))
    request = admin.AdminArtistImportRequest(artist_name="동명이인", scopes=["profile"])
    result = admin.preview_artist_candidates(request)
    assert len(result["candidates"]) == count
    for candidate in result["candidates"]:
        request.identity_confirmation = candidate["confirmation"]
        assert admin._confirmed_identity(request)["id"] == candidate["id"]


def test_commons_source_alone_does_not_confirm_artist_identity(monkeypatch):
    from media_collector import artist_import
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="secret"))
    monkeypatch.setattr(artist_import, "search_artist_candidates", lambda *args: [{
        "id": "Q1", "label": "동명이인", "official_source_urls": [],
        "commons_source_url": "https://commons.wikimedia.org/wiki/Category:Artist",
    }])
    request = admin.AdminArtistImportRequest(
        artist_name="동명이인", scopes=["profile"],
        official_source_urls=["https://commons.wikimedia.org/wiki/Category:Artist"],
    )
    candidate = admin.preview_artist_candidates(request)["candidates"][0]
    assert candidate["can_collect"] is False
    assert candidate["confirmation"] is None


@pytest.mark.parametrize("change", ["missing", "tampered", "expired", "name", "url"])
def test_identity_confirmation_rejects_invalid_choice_before_job(monkeypatch, change):
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="secret"))
    request = admin.AdminArtistImportRequest(artist_name="동명이인", scopes=["profile"])
    request.identity_confirmation = admin._sign_identity(request, {"id": "Q2", "official_source_urls": ["https://example.com"]})
    if change == "missing":
        request.identity_confirmation = None
    elif change == "tampered":
        request.identity_confirmation += "x"
    elif change == "expired":
        now = admin.time.time()
        monkeypatch.setattr(admin.time, "time", lambda: now + 901)
    elif change == "name":
        request.artist_name = "다른 사람"
    else:
        request.official_source_urls = ["https://other.example.com"]
    monkeypatch.setattr(admin, "_create_artist_job", lambda *args, **kwargs: pytest.fail("invalid choice created job"))
    with pytest.raises(HTTPException) as error:
        admin.start_artist_import(request, None)
    assert error.value.status_code == 409


def test_recollection_restores_settings_and_prevents_different_identity(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="secret"))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = {"artist_name": "아이브", "existing_artist_slug": "ive", "scopes": ["albums"],
                "album_limit": 35, "candidate": {"id": "Q123"}}
    with Session(engine, expire_on_commit=False) as session:
        job = CollectionJob(source="artist", query="아이브", status="completed",
                            cursor=json.dumps({"request": settings, "artist_slug": "ive"}))
        session.add(job)
        session.commit()
        detail = admin.artist_import_job(str(job.id), session)
        assert detail["settings"]["album_limit"] == 35
        assert detail["settings"]["scopes"] == ["albums"]
        request = admin.AdminArtistImportRequest(artist_name="아이브", existing_artist_slug="ive", scopes=["albums"], album_limit=60)
        request.identity_confirmation = admin._sign_identity(request, {"id": "Q999"})
        with pytest.raises(HTTPException) as error:
            admin.recollect_artist(str(job.id), request, session)
        assert error.value.status_code == 409
        request.identity_confirmation = admin._sign_identity(request, {"id": "Q123"})
        monkeypatch.setattr(admin, "start_artist_import", lambda request, db: {"album_limit": request.album_limit})
        assert admin.recollect_artist(str(job.id), request, session)["album_limit"] == 60


def test_artist_import_status_callback_requires_internal_key(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="internal-secret"))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        job = CollectionJob(source="artist", query="아이유")
        session.add(job)
        session.commit()
        with pytest.raises(HTTPException) as error:
            admin.update_artist_import_status(
                job.id,
                admin.ArtistImportStatusRequest(status="running", stage="공식 채널 확인", progress=10),
                "wrong-key",
                session,
            )
        assert error.value.status_code == 401

        updated = admin.update_artist_import_status(
            job.id,
            admin.ArtistImportStatusRequest(
                status="completed",
                stage="데이터 반영 완료",
                progress=100,
                collected_count=18,
            ),
            "internal-secret",
            session,
        )

    assert updated["status"] == "completed"
    assert updated["progress"] == 100
    assert updated["collected"] == 18
    assert updated["updated_at"]


def test_completed_artist_can_enable_and_claim_scheduled_refresh(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(internal_api_key="internal-secret"))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = {
        "artist_name": "아이유",
        "existing_artist_slug": "iu",
        "official_source_urls": ["https://www.youtube.com/@dlwlrma"],
        "scopes": ["profile"],
    }
    with Session(engine, expire_on_commit=False) as session:
        job = CollectionJob(
            source="artist",
            query="아이유",
            status="running",
            cursor=json.dumps({"request": payload, "import_kind": "initial"}),
        )
        session.add(job)
        session.commit()
        admin.update_artist_import_status(
            job.id,
            admin.ArtistImportStatusRequest(
                status="completed",
                stage="완료",
                progress=100,
                artist_id=77,
                artist_slug="iu",
            ),
            "internal-secret",
            session,
        )
        schedule = admin.update_artist_refresh_schedule(
            77, admin.ArtistRefreshScheduleRequest(interval_seconds=86400), session
        )
        rule = session.scalar(select(CollectionRule).where(CollectionRule.artist_id == 77))
        rule.next_collect_at = admin.datetime.now(admin.timezone.utc) - admin.timedelta(seconds=1)
        session.commit()
        claimed = admin.claim_due_artist_refreshes("internal-secret", session)
        refresh_job = session.scalar(
            select(CollectionJob)
            .where(CollectionJob.source == "artist", CollectionJob.status == "pending")
            .order_by(CollectionJob.created_at.desc())
        )

    assert schedule["refresh_enabled"] is True
    assert schedule["refresh_interval_seconds"] == 86400
    assert claimed["count"] == 1
    assert claimed["items"][0]["artist_name"] == "아이유"
    assert claimed["items"][0]["job_id"] == refresh_job.id
    assert json.loads(refresh_job.cursor)["import_kind"] == "scheduled_refresh"
