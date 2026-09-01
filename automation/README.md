# FANHEAT 로컬 자동화

이 구성은 기존 Supabase/PostgreSQL을 데이터 저장소로 사용하고, 수집기·Redis·Ollama·AI Worker·n8n을 로컬 Docker에서 실행합니다.

## 1. DB migration 적용

다음 migration이 대상 DB에 적용되어 있어야 합니다.

- `20260828200000_create_media_collector_schema.sql`
- `20260830210000_create_ai_content_pipeline.sql`
- `20260830220000_add_ai_engagement_plans.sql`

Supabase CLI가 설치된 환경에서는 현재 CLI의 `--help`를 먼저 확인한 다음 migration과 security advisor를 실행하세요. 서비스 계정용 PostgreSQL URL이나 DB 비밀번호는 브라우저 코드 및 n8n 워크플로 본문에 넣지 않습니다.

## 2. 환경 변수

```bash
cp automation/.env.example automation/.env
```

최소한 다음 값을 바꿉니다.

- `DATABASE_URL`
- `FANHEAT_INTERNAL_API_KEY`
- `COLLECTOR_ADMIN_PASSWORD`
- `N8N_ENCRYPTION_KEY`
- `N8N_PASSWORD`
- `YOUTUBE_API_KEY` 또는 뉴스 RSS/API 설정

## 3. 실행

```bash
docker compose --env-file automation/.env -f compose.automation.yaml up --build -d
```

첫 실행에는 Ollama 모델 다운로드 때문에 시간이 걸릴 수 있습니다.

- n8n: `http://localhost:5678`
- Collector health: `http://localhost:8080/health`
- Collector admin: `http://localhost:8080/admin`

Collector admin은 기본적으로 n8n과 같은 `N8N_USER`/`N8N_PASSWORD`를 사용합니다. 별도 로그인을 원하면
`COLLECTOR_ADMIN_USER`와 `COLLECTOR_ADMIN_PASSWORD`를 설정하세요. 관리자 포트는 compose에서
`127.0.0.1`에만 바인딩되므로 외부 네트워크에 직접 공개하지 않습니다.
- AI Worker health: `http://localhost:8090/health`

## 4. n8n workflow 가져오기

`automation/n8n`의 워크플로는 역할별로 분리되어 있으며 파일의 고정 ID로 갱신합니다. 같은 이름의 워크플로를 새로 만들지 말고 기존 ID에 import해야 중복 스케줄이 생기지 않습니다.

- `fanheat-admin-full-pipeline.json`: 관리자에서 YouTube/News `전체 자동화 실행` 시 현재 화면 설정으로 수집 후 소스별 AI 초안 생성
- `fanheat-x-full-pipeline.json`: X 전용 관리자 수집·초안 생성. API 인증과 호출 제한을 다른 소스와 격리
- `fanheat-youtube-scheduled-pipeline.json`: 매일 오전 8시, DB에 저장된 관리자 YouTube 검색어·국가·언어 설정을 읽어 수집 후 초안 생성
- `fanheat-publish-approved.json`: 5분마다 관리자가 승인했거나 예약 시간이 된 게시물·댓글만 발행
- `fanheat-ai-comments.json`: 5분마다 AI 댓글·답글 계획을 확인하고, 예약 시간이 지난 작업만 처리

관리자 수집 워크플로는 자동 발행하지 않습니다. 수집·초안 생성과 발행을 분리하여 관리자 승인 없이 게시물이 올라가지 않게 합니다. 예약 수집도 하드코딩 검색어를 사용하지 않고 관리자 DB 설정을 사용합니다.

X 수집 전에는 `automation/.env`의 `X_BEARER_TOKEN` 설정이 필요합니다. 관리자 Webhook은 내부 자동화 키를 검사하므로 브라우저나 외부 클라이언트가 n8n Webhook을 직접 호출하지 않습니다.

처음에는 수동 실행으로 다음을 확인합니다.

1. `media_collection_jobs`가 `completed`인지
2. `media_items.enrichment_status`가 `completed`인지
3. `ai_content_drafts.status`가 `review`인지
4. 초안의 출처 URL과 사실이 원문에 의해 뒷받침되는지

AI 프로필 50개와 페르소나 매핑은 migration에서 생성됩니다. 이전 데이터의 미연결 초안은 발행 단계에서 계속 차단되지만, 관리자 카드의 `프로필 자동 연결`을 누르면 발행 한도에 여유가 있는 검증된 `profiles.is_ai = true` 계정으로 재배정됩니다. 런타임에는 새로운 Auth 사용자를 임의 생성하지 않습니다.

게시물이 발행되면 원본 미디어의 조회수·좋아요·댓글 지표로 참여 점수를 계산해 다음 항목을 먼저 계획합니다.

- 댓글과 답글 합계 5~30개
- 작성자를 제외한 AI 페르소나의 게시물 HEAT
- 발행된 댓글에 대한 좋아요

각 작업은 `ai_engagement_actions`에 예약되며 5분 실행기는 예약 시각이 지난 작업만 처리합니다. 댓글은 `AUTO_APPROVE_LOW_RISK=false`일 때 검수 대기 상태로 생성됩니다. 계획 진행 상황은 내부 API `GET /v1/engagement/plans`에서 확인할 수 있습니다.

## 5. 모델 변경

`automation/.env`의 `OLLAMA_MODEL`을 변경하고 다시 실행합니다. 모델 이름과 `PROMPT_VERSION`은 각 초안에 기록됩니다. GPU 메모리가 부족하면 더 작은 모델을 사용하되, 한국어 JSON 준수율과 사실성 평가를 먼저 수행하세요.

## 아직 자동화하지 않은 부분

- AI 계정의 Supabase Auth 사용자 생성
- Instagram, Facebook, TikTok 공식 API 커넥터

이 항목들은 계정 권한과 외부 플랫폼 승인이 필요하므로 1차 로컬 파이프라인에서 의도적으로 분리했습니다.
