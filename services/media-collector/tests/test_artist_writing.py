from types import SimpleNamespace
import httpx
from media_collector.artist_writing import draft_artist_sections, save_artist_sections


def test_writer_failure_does_not_erase_existing_content(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(httpx, 'post', fail)
    logs=[]
    result=draft_artist_sections({'artist_name':'IVE','scopes':['biography']},[],
        {'source_url':'https://official.test','paragraphs_original':['IVE debuted in December 2021.']},[],
        SimpleNamespace(ai_worker_url='http://worker',internal_api_key='secret'),logs)
    assert result == {}
    assert any('기존 내용 유지' in line for line in logs)


def test_empty_sections_never_update_and_saved_content_is_guarded():
    class DB:
        calls=[]
        def execute(self, sql, values):
            self.calls.append((str(sql),values))
    db=DB()
    save_artist_sections(db,18,{})
    assert db.calls == []
    save_artist_sections(db,18,{'biography':{'entries':[{'text':'소개'}]},'awards':{'entries':[{'year':'2021','text':'수상','source_url':'https://official.test','quote':'근거'}]}})
    assert len(db.calls)==2
    assert 'cardinality(bio_paragraphs)' in db.calls[0][0]
    assert 'jsonb_array_length(award_items)' in db.calls[1][0]
