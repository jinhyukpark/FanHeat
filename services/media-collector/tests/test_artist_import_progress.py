import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from media_collector.models import Base, CollectionJob
from media_collector.artist_import import ImportLog
from media_collector import admin


def test_progress_is_persisted_before_import_finishes(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "jobs.db"}')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        job = CollectionJob(source='artist', query='test', status='running', cursor='{}')
        db.add(job)
        db.commit()
        log = ImportLog(db, job.id)
        log.append('앨범 상세 확인 중')
        with Session(engine) as reader:
            result = reader.get(CollectionJob, job.id)
            assert result.status == 'running'
            assert json.loads(result.cursor)['logs'][-1]['message'] == '앨범 상세 확인 중'


def test_report_and_active_log_are_exposed():
    page = admin.ARTIST_IMPORT_HTML
    assert 'renderReport(job)' in page
    assert '일부 수집 · 보완 필요' in page
    assert 'activeLogJob=String(result.job_id)' in page
    assert '공식 YouTube' in page
    assert admin.ArtistImportStatusRequest(status='completed', report={'quality':'partial'}).report['quality'] == 'partial'
