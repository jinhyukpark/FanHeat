# FANHEAT media pipeline development plan

## 현재 저장소 분석

- `web/`: Vite + React SPA이며 `@supabase/supabase-js`로 Supabase에 직접 접근합니다.
- `supabase/migrations/`: artists, posts, admin RBAC, profile 등 서비스 데이터의 변경 이력이 있습니다.
- 기존 Spring `backend/`는 현재 작업 트리에서 제거 중이므로 collector가 의존할 메인 API는 없습니다.
- 루트 `compose.yaml`은 프런트엔드/Caddy 배포만 담당합니다.

이 때문에 collector를 `services/media-collector`에 자체 Python package, Dockerfile, compose로 두고 Supabase PostgreSQL만 공유하도록 했습니다. 기존 웹 빌드나 제거 중인 backend 파일에는 변경을 가하지 않습니다.

## 완료된 Phase 1 MVP

- FastAPI health/job create/job status/development sync API
- Celery + Redis queue, retry/backoff 기본값, worker/beat 컨테이너
- YouTube `search.list → videos.list` 수집 및 statistics 정규화
- X Recent Search 수집, cursor 및 rate-limit header 포착
- NewsAPI 또는 RSS fallback 수집
- RAW/정규화/metric snapshot 분리 저장과 dedup
- Supabase migration, private RLS/grant 정책
- Connector와 dedup/metric-history 단위 테스트

## 출시 전 작업 순서

### P0 — 개발/스테이징 연결

1. Supabase migration을 스테이징에 적용하고 service role만 CRUD 가능한지 확인합니다.
2. YouTube API key를 secret manager에 등록하고 BTS/IU/BLACKPINK 소량 query로 quota와 결과 품질을 측정합니다.
3. Redis persistent/managed instance와 worker 1개를 배포합니다.
4. FastAPI에 내부 인증을 추가하고 `/sync`를 development에서만 노출합니다.
5. structured logging, queue age, success ratio, 429 alert를 연결합니다.

완료 기준: 24시간 동안 중복 media item 없이 주기 수집이 돌고, 실패 job의 원인과 재처리 여부를 추적할 수 있음.

### P1 — YouTube 완성

1. `commentThreads.list`와 `comments.list`용 별도 job/cursor/table을 추가합니다.
2. quota unit budget을 rule/source 단위로 계산하여 quota 부족 시 다음 날로 예약합니다.
3. 인기/일반/오래된 콘텐츠별 metric refresh cadence를 분리합니다.
4. 삭제·비공개 영상 tombstone과 데이터 보존 정책을 구현합니다.
5. artist alias 사전으로 초기 entity mapping을 추가합니다.

완료 기준: 영상/댓글/reply와 24시간 metric curve를 재시작 후에도 이어서 수집.

### P2 — X와 News 운영화

1. X 429 reset header 기반 ETA 재예약, `since_id`, query별 cursor를 rule에 저장합니다.
2. X access tier별 최근 검색 범위를 검증하고 retention 정책을 문서화합니다.
3. RSS feed allowlist, canonical URL, UTM 제거, 동일 기사 hash dedup을 추가합니다.
4. NewsAPI rate limit과 source별 이용약관/전문 저장 허용 범위를 기록합니다.

### P3 — AI worker 분리

1. `media-enrichment` queue와 별도 `services/ai-worker`를 만듭니다.
2. language → artist/entity → topic → sentiment → toxicity → summary 순으로 처리합니다.
3. model/prompt/version을 enrichment 결과에 저장하고 재처리 가능하게 합니다.
4. 검수 상태가 완료된 `media_feed_items` view/RPC만 웹에 노출합니다.

### P4 — Heat/Viral score

1. metric snapshot의 source별 정규화와 속도/가속도 feature를 정의합니다.
2. 신규 콘텐츠 cold-start와 bot/anomaly 필터를 적용합니다.
3. score 버전과 계산 근거를 저장하고 offline backtest를 수행합니다.

## 명시적으로 제외한 범위

- Instagram/Facebook connector와 HTML 무단 크롤러
- 외부 SNS에서 사람인 것처럼 행동하는 AI 계정
- AI like/vote를 실제 사용자 지표와 합산하는 기능
- 웹 feed UI 직접 연결: moderation/enrichment와 공개용 RLS 계약 이후 진행
