"""Prepare retrieved evidence for the configured AI worker and retain provenance."""
import json
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text


def draft_artist_sections(request, pages, profile, news, settings, logs):
    from .artist_import import _collect_artist_source
    selected = set(request.get('scopes', [])) & {'biography', 'history', 'awards'}
    result = {}
    if not selected:
        return result
    sources = []
    if profile.get('paragraphs_original') and profile.get('source_url'):
        sources.append({'url': profile['source_url'], 'text': ' '.join(profile['paragraphs_original'])[:6000]})
    # Only fetched article bodies are evidence, never search headlines alone.
    extra = []
    for item in news[:4]:
        try:
            logs.append('소개·연혁·수상 기사 본문 확인: ' + item['url'])
            extra.extend(_collect_artist_source(item['url'], 12, logs))
        except (httpx.HTTPError, ValueError, OSError):
            logs.append('기사 본문 접근 실패 · 근거에서 제외')
    for page in [*pages, *extra]:
        soup = BeautifulSoup(page.get('html', ''), 'html.parser')
        for node in soup.select('script,style,nav,footer,header'):
            node.decompose()
        body = soup.select_one('article,main') or soup
        content = body.get_text(' ', strip=True)
        if len(content) >= 40:
            sources.append({'url': page['url'], 'text': content[:6000]})
    sources = list({s['url']: s for s in sources if len(s['text']) >= 20}.values())[:20]
    for scope in sorted(selected):
        if not sources:
            logs.append(f'LLM {scope}: 본문 근거 없음 · 기존 내용 유지')
            continue
        logs.append(f'LLM {scope} 작성 시작 · 본문 출처 {len(sources)}개')
        try:
            response = httpx.post(settings.ai_worker_url.rstrip('/')+'/v1/artists/write',
                headers={'X-FANHEAT-API-KEY': settings.internal_api_key or ''},
                json={'artist_name': request['artist_name'], 'language': request.get('language_code','ko'),
                      'scope': scope, 'sources': sources}, timeout=180)
            response.raise_for_status()
            data = response.json()
            result[scope] = data
            logs.append(f"LLM {scope} 작성 완료 · {len(data.get('entries', []))}개 · 근거 검증 제외 {data.get('rejected',0)}개 · 관리자 검토 필요")
        except (httpx.HTTPError, ValueError):
            logs.append(f'LLM {scope} 작성 실패 · 기존 내용 유지, 재수집 필요')
    return result


def save_artist_sections(db, artist_id, sections):
    # Fill missing fields only. Human edits and previously published copy remain intact.
    for scope, column in [('biography','bio_paragraphs'),('history','history_items'),('awards','award_items')]:
        entries = sections.get(scope, {}).get('entries') or []
        if not entries:
            continue
        if scope == 'biography':
            db.execute(text('update public.artists set bio_paragraphs=:items, updated_at=now() where id=:id and coalesce(cardinality(bio_paragraphs),0)=0'),
                       {'id':artist_id,'items':[e['text'] for e in entries]})
        else:
            db.execute(text(f"update public.artists set {column}=cast(:items as jsonb), updated_at=now() where id=:id and coalesce(jsonb_array_length({column}),0)=0"),
                       {'id':artist_id,'items':json.dumps(entries,ensure_ascii=False)})
