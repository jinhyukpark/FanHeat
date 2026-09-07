import base64
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlparse
import httpx
from sqlalchemy import text


def fetch_image(url):
    from .artist_import import _public_https_url
    # Wikimedia rejects anonymous/default HTTP clients with 403. Identify this
    # bounded fetch just as the Commons metadata client does.
    headers = {"User-Agent": "FANHEAT-Artist-Collector/1.0 (https://fanheat.com)"}
    with httpx.Client(timeout=12, follow_redirects=False, headers=headers) as client:
        for _ in range(4):
            _public_https_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location',''))
                    continue
                response.raise_for_status()
                if response.headers.get('content-type','').split(';')[0] not in {'image/jpeg','image/png','image/webp'}:
                    raise ValueError('unsupported image format')
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>4_000_000:
                        raise ValueError('image size limit')
                return base64.b64encode(data).decode()
    raise ValueError('too many redirects')


def classify_gallery(request, pages, settings, logs, extra_candidates=None):
    candidates={}
    for item in extra_candidates or []:
        if item.get('image_url') and item.get('source_url'):
            candidates.setdefault(item['image_url'], item)
    # Only images embedded in the supplied official pages; no image-search results.
    for page in pages:
        for image in page.get('images',[]):
            candidates.setdefault(image, {'source_url':page['url'], 'source_provider':'official_site',
                                           'original_image_url':image})
    results=[]; started=time.monotonic()
    # The UI already allows up to 200, but a single run needs a bounded vision
    # budget. Twenty-four candidates is enough to retain variety while avoiding
    # an unbounded local-model job.
    limit=min(int(request.get('gallery_limit',40)),24)
    for url,metadata in list(candidates.items())[:limit]:
        if time.monotonic()-started>240:
            break
        logs.append('비전 모델 이미지 확인: '+url)
        try:
            data=fetch_image(url)
            response=httpx.post(settings.ai_worker_url.rstrip('/')+'/v1/artists/classify-image',
                json={'image_base64':data},headers={'X-FANHEAT-API-KEY':settings.internal_api_key or ''},timeout=100)
            response.raise_for_status()
            verdict=response.json()
            if verdict.get('decision') not in {'photo_candidate','review','exclude'}:
                raise ValueError('invalid verdict')
        except (httpx.HTTPError,ValueError,OSError):
            verdict={'decision':'review','reason':'이미지 접근 또는 비전 판별 실패 · 자동 추가 안 함'}
        results.append(verdict|metadata|{'image_url':url, 'source_collected_at': datetime.now(timezone.utc).isoformat()})
        logs.append('갤러리 '+verdict['decision']+': '+verdict.get('reason','')+' · 원본: '+url+' · 출처 페이지: '+metadata['source_url'])
    remaining=max(0,len(candidates)-len(results))
    logs.append(f'이미지 판별 {len(results)}개 · 미검토 {remaining}개 · 기존 이미지 삭제 없음')
    return {'items':results,'remaining':remaining,'review_required':True,'storage':'source_url_only'}


def save_gallery_candidates(db, artist_id, report):
    count=0
    for item in report.get('items',[]):
        if item.get('decision') not in {'photo_candidate', 'review', 'exclude'} or not item.get('image_url'):
            continue
        existing=db.execute(text('select id from public.artist_gallery_items where artist_id=:id and image_url=:url'),
                            {'id':artist_id,'url':item['image_url']}).first()
        params = {
            'id': existing.id if existing else artist_id,
            'url': item['image_url'],
            'source': item.get('source_url'),
            'original': item.get('original_image_url') or item['image_url'],
            'collected_at': item.get('source_collected_at'),
            'provider': item.get('source_provider'),
            'creator': item.get('creator_name'),
            'license': item.get('license_name'),
            'license_url': item.get('license_url'),
            'attribution': item.get('attribution_text'),
            'verified': item.get('source_collected_at') if item.get('license_name') else None,
            'decision': item['decision'],
            'reason': item.get('reason'),
            'confidence': item.get('confidence'),
            'category': item.get('category'),
            'people_visible': item.get('people_visible'),
            'promotional_layout': item.get('promotional_layout'),
        }
        if existing:
            # Fill missing provenance only; do not overwrite administrator edits.
            db.execute(text('update public.artist_gallery_items set source_page_url=coalesce(source_page_url,:source), original_image_url=coalesce(original_image_url,:original), source_collected_at=coalesce(source_collected_at,:collected_at), source_provider=coalesce(source_provider,:provider), creator_name=coalesce(creator_name,:creator), license_name=coalesce(license_name,:license), license_url=coalesce(license_url,:license_url), attribution_text=coalesce(attribution_text,:attribution), rights_verified_at=coalesce(rights_verified_at,:verified), ai_decision=:decision, ai_reason=:reason, ai_confidence=:confidence, ai_category=:category, ai_people_visible=:people_visible, ai_promotional_layout=:promotional_layout, review_status=case when active then \'approved\' when review_status in (\'approved\',\'rejected\') then review_status else \'pending\' end, updated_at=now() where id=:id'), params)
            continue
        title = {
            'photo_candidate': '재사용 허용 활동 사진 · 확인 필요' if item.get('source_provider') == 'wikimedia_commons' else '공식 활동 사진 · 확인 필요',
            'review': 'AI 판별 보류 이미지 · 확인 필요',
            'exclude': 'AI 제외 권고 이미지 · 확인 필요',
        }[item['decision']]
        db.execute(text('insert into public.artist_gallery_items(artist_id,title,image_url,active,display_order,source_page_url,original_image_url,source_collected_at,source_provider,creator_name,license_name,license_url,attribution_text,rights_verified_at,ai_decision,ai_reason,ai_confidence,ai_category,ai_people_visible,ai_promotional_layout,review_status) values(:id,:title,:url,false,0,:source,:original,:collected_at,:provider,:creator,:license,:license_url,:attribution,:verified,:decision,:reason,:confidence,:category,:people_visible,:promotional_layout,\'pending\')'), params | {'title': title})
        count+=1
    return count


def representative_photo(report):
    """Only reuse-licensed Commons photos may become automatic profile artwork."""
    non_portrait_markers = {
        'advertisement', 'advertisment', 'album_cover', 'cover)', 'cover.',
        'fileicon-', 'logo', 'repackage', 'rice_wreath', 'title_card',
        'timeline',
    }

    def looks_like_portrait(item):
        searchable = unquote(' '.join(str(item.get(key) or '') for key in (
            'image_url', 'original_image_url', 'source_url', 'title',
        ))).lower().replace(' ', '_')
        return not any(marker in searchable for marker in non_portrait_markers)

    candidates = [item for item in report.get('items', [])
                  if item.get('decision') == 'photo_candidate'
                  and item.get('category') in {'photoshoot', 'activity_photo'}
                  and item.get('people_visible') is True
                  and item.get('promotional_layout') is False
                  and item.get('confidence', 0) >= .85
                  and item.get('source_provider') == 'wikimedia_commons'
                  and item.get('creator_name')
                  and item.get('license_name')
                  and item.get('license_url')
                  and item.get('source_url') and item.get('image_url')
                  and looks_like_portrait(item)]
    candidates.sort(key=lambda item: (item['category'] == 'photoshoot', item['confidence']), reverse=True)
    return candidates[0] if candidates else None
