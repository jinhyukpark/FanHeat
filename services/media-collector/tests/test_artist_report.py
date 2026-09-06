import json
from types import SimpleNamespace
from media_collector.artist_report import completion_issues
from media_collector.admin import _artist_job_payload


def test_detailed_gaps_and_gallery_counts():
    report = {'missing': ['공식 영상 미연결 1곡', '갤러리 원본 검증·서버 저장 보완 필요', 'history 본문 근거 부족 또는 LLM 작성 실패'],
              'evidence': [{'title': 'Album', 'tracks': [{'title': 'Song', 'url': ''}]}],
              'gallery_review': {'storage': 'source_url_only', 'remaining': 5, 'items': [{'decision': 'exclude'}, {'decision': 'review'}, {'decision': 'photo_candidate'}]}}
    issues = completion_issues(report)
    assert 'Album / Song' in issues[0]['detail']
    assert '활동 사진 후보 1개' in issues[1]['detail']
    assert '미검토 5개' in issues[1]['detail']
    assert 'URL만' in issues[1]['detail']
    assert '연혁' in issues[2]['detail']
    assert '구분할 수 없습니다' in issues[2]['detail']
    assert all(i['action'] for i in issues)


def test_historical_report_explained_without_mutation_or_duplicate_logs():
    cursor = json.dumps({'report': {'quality': 'partial', 'missing': ['데뷔·소속사·팬덤 검증 보완 필요']}, 'logs': [{'message': '원래 로그'}]})
    job = SimpleNamespace(cursor=cursor, id='job', query='Artist', status='completed', collected_count=1, error_message=None, created_at=None, updated_at=None, started_at=None, completed_at=None)
    first = _artist_job_payload(job)
    assert first == _artist_job_payload(job)
    assert job.cursor == cursor
    assert first['logs'][0]['message'] == '원래 로그'
    assert first['logs'][-1]['level'] == 'warning'
    assert '조치:' in first['logs'][-1]['message']
    assert '모든 값이 비어' in first['completion_issues'][0]['detail']


def test_complete_and_legacy_reports():
    assert completion_issues(None) == []
    assert completion_issues({'quality': 'complete'}) == []
    assert completion_issues({'missing': ['새로운 사유']})[0]['detail'] == '새로운 사유'
