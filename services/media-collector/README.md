# FANHEAT Media Collector

FANHEAT의 웹 앱과 독립적으로 배포되는 외부 미디어 수집 서비스입니다. Phase 1은 YouTube, X, News/RSS를 하나의 정규화 스키마로 저장하며 YouTube 경로를 우선 구현합니다.

## 실행 구성

- `api`: 작업 생성/조회 및 개발용 동기 실행 API
- `worker`: Redis 큐에서 수집 작업 실행
- `beat`: 등록된 주기 작업 발행
- `connectors`: 플랫폼 API 응답을 `MediaContent`로 변환
- PostgreSQL/Supabase: RAW, 정규화 데이터, 지표 snapshot 저장

## 빠른 시작

Python 3.12 이상에서:

```bash
cd services/media-collector
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
media-collector init-db
uvicorn media_collector.main:app --reload --port 8080
```

별도 터미널에서 큐 worker를 실행합니다.

```bash
celery -A media_collector.celery_app:celery_app worker -Q media-collection --loglevel=INFO
```

전체 로컬 인프라는 `docker compose -f services/media-collector/compose.yaml up --build`로 실행할 수 있습니다. Supabase를 사용할 때는 `DATABASE_URL`을 Supabase의 direct/session pooler PostgreSQL URL로 바꾸고 migration을 먼저 적용합니다. 브라우저용 publishable key가 아니라 DB 비밀번호 또는 안전하게 보관된 서비스 자격 증명을 사용해야 합니다.

## API

수집 관리자에서 선택한 국가와 우선 언어는 `media_collector_settings`에 저장됩니다. 요청에서
`region_code`/`language_code`를 생략하면 API와 n8n 작업 모두 이 저장값(초기값 `KR`/`ko`)을
사용합니다. YouTube 수집에는 각각 `regionCode`와 `relevanceLanguage`로 전달됩니다.
관리자 화면의 언어 적용 방식은 `language_filter_mode`로 저장되어 n8n에도 전달됩니다.
`prefer`는 요청 언어와 일치하는 결과를 먼저 보여 주고, `strict`는 요청 언어의 메타데이터가
없는 결과를 제외합니다. 단, 영문 제목을 사용하는 한국 공식 방송사·기획사 K-POP 채널은
`strict`에서도 수집합니다. YouTube 검색 힌트만으로는 언어가 강제되지 않으므로 후보를 최대
50개까지 조회한 뒤 이 정책을 적용해 요청한 최종 개수만 저장합니다.

큐 기반 작업 생성:

```bash
curl -X POST http://localhost:8080/v1/collections \
  -H 'content-type: application/json' \
  -d '{"source":"youtube","query":"BTS","max_results":25}'
```

작업 조회:

```bash
curl http://localhost:8080/v1/collections/JOB_ID
```

개발 환경 동기 실행:

```bash
curl -X POST http://localhost:8080/v1/collections/sync \
  -H 'content-type: application/json' \
  -d '{"source":"news","query":"BLACKPINK"}'
```

CLI 한 번 실행:

```bash
media-collector collect youtube "BTS" --max-results 10
```

## 자격 증명과 제한

- YouTube: `YOUTUBE_API_KEY`; `search.list` 후 `videos.list`로 snippet/statistics를 보강합니다.
- X: `X_BEARER_TOKEN`; Recent Search 접근 권한이 필요합니다. cursor 및 rate-limit header를 Connector 결과에 포함합니다.
- News: `NEWS_API_KEY`가 있으면 NewsAPI를 사용하고, 없으면 `NEWS_RSS_FEEDS`의 쉼표 구분 RSS 목록을 검색합니다.
- 외부 API의 이용약관, 보존 정책, 삭제 요청을 운영 정책에 반영해야 합니다. HTML 무단 수집은 이 MVP에 포함하지 않습니다.

## 검증

```bash
cd services/media-collector
pytest
```

상세 설계와 단계별 계획은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)를 참고하세요.
