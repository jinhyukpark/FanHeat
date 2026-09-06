from types import SimpleNamespace
import httpx
from media_collector.gallery_vision import classify_gallery, save_gallery_candidates
from media_collector.gallery_vision import representative_photo
from media_collector.artist_import import ArtistPageParser, collect_gallery_pages


def test_representative_requires_verified_photo_and_prefers_portrait():
    photo = {'decision':'photo_candidate','category':'activity_photo','people_visible':True,'promotional_layout':False,'confidence':.95,'source_url':'https://official.test/profile','image_url':'https://official.test/activity.jpg'}
    portrait = photo | {'category':'photoshoot','image_url':'https://official.test/portrait.jpg'}
    assert representative_photo({'items':[photo,portrait]}) == portrait
    for change in [{'category':'logo'},{'promotional_layout':True},{'people_visible':False},{'confidence':.4},{'decision':'review'}]:
        assert representative_photo({'items':[photo | change]}) is None


def test_model_failure_never_accepts_image(monkeypatch):
    monkeypatch.setattr('media_collector.gallery_vision.fetch_image',lambda url:'encoded')
    def fail(*args,**kwargs):
        raise httpx.ConnectError('down')
    monkeypatch.setattr(httpx,'post',fail)
    result=classify_gallery({'gallery_limit':2},[{'url':'https://official.test','images':['https://official.test/1.png']}],
        SimpleNamespace(ai_worker_url='http://worker',internal_api_key='secret'),[])
    assert result['items'][0]['decision']=='review'


def test_gallery_reviews_more_than_old_twelve_candidate_cap(monkeypatch):
    monkeypatch.setattr('media_collector.gallery_vision.fetch_image', lambda url: 'encoded')
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {'decision':'exclude','reason':'not a photo'},
    ))
    images = [f'https://official.test/{index}.jpg' for index in range(20)]
    result = classify_gallery({'gallery_limit':40}, [{'url':'https://official.test/gallery','images':images}],
        SimpleNamespace(ai_worker_url='http://worker',internal_api_key='secret'), [])
    assert len(result['items']) == 20
    assert result['remaining'] == 0


def test_official_lazy_images_and_photo_pages_are_collected(monkeypatch):
    parser = ArtistPageParser('https://official.test/')
    parser.feed('<img data-src="/lazy.jpg"><img srcset="/small.jpg 1x, /large.jpg 2x">')
    assert 'https://official.test/lazy.jpg' in parser.images
    assert 'https://official.test/large.jpg' in parser.images

    photo = {'url':'https://official.test/gallery','images':['https://official.test/group.jpg'],'links':[]}
    monkeypatch.setattr('media_collector.artist_import._collect_artist_source', lambda *args: [photo])
    pages = [{'url':'https://official.test/','images':[],'links':[
        'https://official.test/gallery', 'https://official.test/shop', 'https://outside.test/photo']}]
    result = collect_gallery_pages(pages, [])
    assert result[0] == photo
    assert len(result) == 2


def test_gallery_only_inserts_candidates_as_private_without_deletes():
    class DB:
        calls=[]
        params=[]
        def execute(self,sql,params):
            self.calls.append(str(sql))
            self.params.append(params)
            return SimpleNamespace(first=lambda:None)
    db=DB()
    count=save_gallery_candidates(db,18,{'items':[{'decision':'exclude'},{'decision':'review'},
        {'decision':'photo_candidate','image_url':'https://official.test/photo.jpg', 'source_url':'https://official.test/photos/1', 'source_collected_at':'2026-09-06T00:00:00Z'}]})
    assert count==1
    assert 'false' in db.calls[-1]
    assert not any('delete' in q or 'update' in q for q in db.calls)
    assert db.params[-1]['source']=='https://official.test/photos/1'
    assert db.params[-1]['collected_at']=='2026-09-06T00:00:00Z'
    assert 'original_image_url' in db.calls[-1]


def test_recollection_fills_only_missing_provenance():
    class DB:
        calls=[]
        def execute(self,sql,params):
            self.calls.append(str(sql))
            return SimpleNamespace(first=lambda:SimpleNamespace(id=99))
    db=DB()
    assert save_gallery_candidates(db,18,{'items':[{'decision':'photo_candidate','image_url':'https://official.test/p.jpg','source_url':'https://official.test/photos'}]})==0
    assert 'coalesce(source_page_url,:source)' in db.calls[-1]
    assert not any('insert' in q or 'delete' in q for q in db.calls)
