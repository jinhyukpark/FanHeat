# Media Collector architecture

## 1. 요구사항과 경계

### 기능 요구사항

- 아티스트/키워드 기준 YouTube, X, News/RSS 검색
- 원본 payload 보존, 공통 `MediaContent` 변환, `(source, source_content_id)` 중복 제거
- 조회·좋아요·댓글·공유 수치의 시계열 snapshot 축적
- pagination cursor와 작업 성공/실패 이력 보존
- API 요청과 실제 외부 수집을 Redis queue로 분리
- AI 분석은 별도 worker가 소비할 수 있도록 `enrichment_status` 제공

### 비기능 요구사항과 가정

- 초기 규모: 아티스트 수십 명, source별 분 단위 수집, 하루 수만 건 이하
- 외부 API latency와 quota가 전체 지연의 주원인이므로 사용자 요청 경로에서 동기 호출하지 않음
- at-least-once delivery를 허용하고 DB unique key/upsert로 멱등성 확보
- FANHEAT 웹은 현재 Supabase에 직접 연결되므로 RAW 데이터는 anon/authenticated에 공개하지 않음
- API key는 서버 환경 변수/secret manager에만 저장

## 2. 구성과 데이터 흐름

```text
Admin/Scheduler
      |
      v
 FastAPI -----> media_collection_jobs
      |
      v
 Redis queue <----- Celery Beat
      |
      v
 Collector Worker
      |
      +---- YouTube Connector (search -> videos/statistics)
      +---- X Connector       (recent search + cursor/rate-limit)
      +---- News Connector    (NewsAPI or RSS)
      |
      v
 media_raw_items
      |
      v
 Normalize + idempotent upsert
      |
      +---- media_items ----------------> future AI queue/worker
      |
      +---- media_metric_snapshots -----> Viral/Heat score
```

Collector는 수집·정규화·저장까지만 담당합니다. sentiment, entity linking, summary, embedding은 별도 `ai-worker` 배포 단위가 `enrichment_status=pending` 레코드를 queue로 받아 처리합니다. 이 경계는 수집 quota 장애가 AI 처리량을 잠식하지 않게 합니다.

## 3. 공통 계약

`MediaContent`의 필수 identity는 `source + source_content_id`입니다. `author`와 `metrics`는 source 차이를 JSON 객체로 흡수하되, 검색과 정렬에 필요한 `published_at`, `content_type`, `source`는 typed column으로 둡니다.

```json
{
  "source": "youtube",
  "source_content_id": "abc123",
  "content_type": "video",
  "author": {"source_id": "channel123", "name": "HYBE LABELS"},
  "title": "...",
  "text": "...",
  "url": "https://www.youtube.com/watch?v=abc123",
  "thumbnail_url": "https://...",
  "published_at": "2026-08-28T00:00:00Z",
  "metrics": {"views": 1200000, "likes": 82000, "comments": 11000, "shares": null},
  "entities": ["BTS", "Jungkook"]
}
```

## 4. DB 스키마

| Table | 목적 | 핵심 제약/인덱스 |
|---|---|---|
| `media_collection_rules` | 아티스트별 query와 실행 주기 | due partial index, source/query/artist unique |
| `media_collection_jobs` | 실행 상태, cursor, 오류, 수집량 | status/source index |
| `media_raw_items` | source 원본 JSON과 변경 hash | source/content unique |
| `media_items` | 플랫폼 공통 서비스/AI 입력 | source/content unique, published/source index, entities GIN |
| `media_metric_snapshots` | engagement 시계열 | item/captured descending index |

RAW와 정규화 레코드는 서로 다른 수명주기를 가질 수 있습니다. 초기에는 모두 PostgreSQL에 두되 RAW 증가량이 커지면 payload를 S3 호환 object storage로 옮기고 DB에는 object key와 hash만 남깁니다.

모든 collector table은 RLS가 활성화되며 anon/authenticated 권한이 revoke됩니다. feed 노출은 검수·AI 처리가 끝난 데이터를 반환하는 별도 view/RPC 또는 메인 API로 제한합니다.

## 5. Queue와 실패 정책

### Queue

- `media-collection`: source 수집 작업. `acks_late`, prefetch 1로 긴 작업의 공정성을 확보합니다.
- 향후 `media-enrichment`: language/entity/topic/sentiment/summary 작업.
- 트래픽 증가 시 `media-youtube`, `media-x`, `media-news` queue로 route만 분리하며 서비스 코드는 유지합니다.

### 멱등성과 재시도

1. job이 `pending → running`으로 전환됩니다.
2. Connector 호출 실패 시 job을 `failed`로 기록합니다.
3. network/timeout 계열은 exponential backoff + jitter로 최대 5회 재시도합니다.
4. 429는 source의 reset header까지 countdown하여 재예약하는 정책을 다음 hardening 단계에서 추가합니다.
5. worker 중단으로 동일 작업이 재전달돼도 unique key가 media item 중복을 막습니다. metric snapshot은 관측 이력이므로 실행마다 추가됩니다.

운영에서는 credential 오류/400은 재시도하지 않고, 429/5xx/network만 재시도 대상으로 분류해야 합니다. 현재 MVP는 connector 오류를 job에 보존하고 network 계열 자동 재시도를 제공합니다.

## 6. API 계약

- `POST /v1/collections`: job 생성 후 queue publish, `202`
- `GET /v1/collections/{job_id}`: 상태/cursor/error 조회
- `POST /v1/collections/sync`: 로컬 개발 및 제한된 관리자 진단용
- `GET /health`: DB 연결과 버전 확인

운영 배포 시 API는 private network에 두거나 service-to-service 인증을 붙이고 `/sync` endpoint를 비활성화합니다.

## 7. 관측성과 보안

- 로그 key: `job_id`, `source`, `query_hash`, `attempt`, `latency_ms`, `upstream_status`, `quota_remaining`
- 지표: job success ratio, items/job, duplicate ratio, queue age, connector latency, 429/5xx count
- 경보: queue age 10분 초과, source별 연속 실패, quota 20% 이하, job failure ratio 5% 초과
- source payload에 개인정보가 포함될 수 있으므로 로그에 원문/token을 남기지 않고 보존·삭제 정책을 둡니다.
- Supabase publishable key를 collector에서 사용하지 않으며 DB secret은 secret manager에서 주입합니다.

## 8. 확장 시 재검토할 결정

- 하루 RAW 수백만 건: payload object storage 전환 및 월별 partition
- source별 SLA/처리량 차이 확대: connector queue/worker 독립 scale-out
- 복잡한 장기 workflow: Celery에서 Temporal로 전환 검토
- metrics 분석량 증가: TimescaleDB 또는 warehouse 복제
- feed 실시간성 요구: PostgreSQL outbox + event bus 도입
- 다국가 개인정보 요구: source별 retention/deletion workflow 분리
