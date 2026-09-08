# FANHEAT 로컬 자동화

이 구성은 기존 Supabase/PostgreSQL을 데이터 저장소로 사용하고, 수집기·Redis·Ollama·AI Worker·n8n을 로컬 Docker에서 실행합니다.

## 1. DB migration 적용

다음 migration이 대상 DB에 적용되어 있어야 합니다.

- `20260828200000_create_media_collector_schema.sql`
- `20260830210000_create_ai_content_pipeline.sql`
- `20260830220000_add_ai_engagement_plans.sql`

Supabase CLI가 설치된 환경에서는 현재 CLI의 `--help`를 먼저 확인한 다음 migration과 security advisor를 실행하세요. 서비스 계정용 PostgreSQL URL이나 DB 비밀번호는 브라우저 코드 및 n8n 워크플로 본문에 넣지 않습니다.

`FANHEAT AI engagement` 워크플로는 5분마다 AI Worker의 참여 러너를 호출합니다. 러너는 게시물 댓글·답글·HEAT·댓글 좋아요뿐 아니라 AI 페르소나별 확률에 따른 인기 아티스트 팔로우와 FAN 등록, AI 계정이 받은 친구 요청 판단을 담당합니다. 아티스트 행동은 서울 날짜 기준 페르소나당 하루 한 번만 결정합니다. 친구 요청은 AI 페르소나별로 하루 한 번 수락 여부를 판단하며, 보류된 요청은 다음 날 다시 판단합니다. 선택하지 않은 결정도 감사 로그에 남깁니다.

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
- 한국 네이버 뉴스 검색을 사용할 경우 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- NAVER Cloud의 NAVER API HUB 키는 `NAVER_API_PROVIDER=api_hub`로 설정합니다.
  기존 developers.naver.com 검색 애플리케이션 키만 `developers`를 사용합니다.
- 같은 키의 `검색어 트렌드` 권한을 사용해 최근 30일 국내 K-POP 검색량을 분석합니다. 추천 결과는 6시간 캐시되며 YouTube, News/RSS, X 작업 설정에 공통 반영됩니다.

Collector의 아티스트 자동화 Webhook은 기본적으로
`http://n8n:5678/webhook/fanheat-artist-import`를 사용합니다. 별도 n8n 호스트를 쓰는 경우
Collector 환경의 `N8N_ARTIST_WEBHOOK_URL`을 변경합니다.

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
- `fanheat-youtube-scheduled-pipeline.json`: 비활성 보관 워크플로. 사용자 실행 없이 수집·초안 생성을 시작하지 않도록 활성화하지 않습니다.
- `fanheat-publish-approved.json`: 1분마다 예약 시각을 확인하고, 관리자 수동 승인 또는 `전체 자동화 실행`으로 정책 승인된 포스트만 8~26분의 불규칙한 간격으로 한 건씩 발행
- `fanheat-ai-comments.json`: 5분마다 AI 댓글·답글·HEAT·댓글 좋아요를 처리하고, 하루 한 번 페르소나 성향에 따라 인기 아티스트 팔로우와 FAN 등록 여부를 결정
- `fanheat-ai-daily-votes.json`: 매시간 누락 여부를 확인하고 활성 AI 계정마다 서울 날짜 기준 하루 한 표만 생성
- `fanheat-artist-profile-import.json`: 공식 프로필·SNS 근거, 앨범 상세·수록곡과 공식 YouTube 연결을 수집합니다. 작업 종료와 데이터 충족도를 별도로 보고합니다.
- `fanheat-artist-scheduled-refresh.json`: 수집 완료 아티스트별 갱신 주기를 5분마다 확인하고, 갱신 시각이 된 아티스트만 공식 채널에서 다시 수집
- 아티스트 정보 자동화는 Collector Studio의 `아티스트 정보 가져오기` 화면에서
  `POST /webhook/fanheat-artist-import`로 시작합니다. 워크플로는 전달받은 `job_id`를 유지하고,
  각 단계에서 `POST /admin/api/artist-imports/{job_id}/status`를 호출해 진행률을 보고해야 합니다.
  이 콜백의 `X-FANHEAT-API-KEY` 헤더에는 `FANHEAT_INTERNAL_API_KEY` 값을 사용합니다.
  요청 본문에는 아티스트 이름과 기존 slug, 공식 채널 URL, 언어, 수집 범위,
  앨범·갤러리 제한, 이미지 저장 버킷, 검토 후 공개 여부가 포함됩니다. 공식 채널 URL은
  HTTPS만 허용하며 로컬·사설 IP는 Collector에서 거부합니다.

`수집만 실행`은 미디어만 저장하고 AI 초안·승인·발행을 시작하지 않습니다. `전체 자동화 실행`은 명시적으로 시작한 실행에만 `admin_full_automation` 출처를 기록하며, 저위험 초안의 정책 승인과 예약 발행을 허용합니다. 백그라운드 발행기는 관리자 수동 승인 건과 이 출처의 정책 승인 건만 처리합니다.

News/RSS 화면의 `수집 허용 언론사`에는 언론사명, 기사 원문 도메인, 선택 RSS HTTPS 주소를 저장할 수 있습니다. 한 곳 이상 등록하면 기사 URL의 호스트가 허용 도메인과 일치하는 결과만 수집하며, 이 목록은 관리자 전체 자동화 요청에서 n8n을 거쳐 Collector까지 전달됩니다. 기사 이미지는 갤러리로 복제하지 않습니다. 관리자가 해당 언론사의 `RSS/API·OpenGraph 썸네일 허용`을 켜면 RSS/API 이미지가 없는 경우에도 기사 원문의 `og:image` 또는 `twitter:image`를 확인해 링크 카드 미리보기 주소로 저장합니다. 기사와 썸네일은 공개 HTTPS 주소만 허용하며, 이동 후 기사 도메인도 허용 목록과 다시 대조합니다.

News/RSS 수집 화면의 `뉴스 수집 시작일`과 `뉴스 수집 종료일`은 한국 시간 기준의 포함 범위입니다. 직접 수집과 관리자 전체 자동화 모두 같은 범위를 사용하며, n8n은 계산된 UTC `published_after`/`published_before` 값을 Collector에 그대로 전달합니다. Naver News Search는 기간 파라미터가 없으므로 Collector가 최신순 결과를 페이지 단위로 탐색한 뒤 선택 기간 밖의 기사를 제외합니다(검색 API가 제공하는 최대 결과 범위 내).

YouTube 수집 기간은 `1일`, `1주`, `2주`, `1개월`, `3개월`, `6개월`, `12개월` 프리셋을 제공합니다. `기타 날짜 선택`은 한국 시간 기준의 포함 범위로 계산되며, 직접 수집과 관리자 전체 자동화에 동일하게 적용됩니다.

TikTok은 NAVER_CLIENT_ID/SECRET의 웹문서 검색 권한으로 키워드에 맞는 공개 영상 링크를 찾고 공식 oEmbed 정보를 확인합니다. 기존 n8n 전체 자동화가 같은 수집기를 호출하며 Research API 키는 사용하지 않습니다. TikTok 검색 페이지를 크롤링하거나 영상 파일을 복제하지 않습니다. 검색 색인에 없는 영상은 발견할 수 없고 게시일·국가·조회수 정렬은 지원하지 않습니다. 저장 날짜는 발견 시각입니다. oEmbed 성공은 실제 재생 성공이나 사용 권한을 보장하지 않으므로 관리자 검수가 필요합니다. 403·429·서버 오류는 영상 삭제로 처리하지 않고 작업 오류로 표시합니다.

`NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`이 설정된 한국 수집은 네이버 뉴스 검색 API를 우선 사용합니다. NAVER API HUB 모드는 `https://naverapihub.apigw.ntruss.com/search/v1/news`와 `X-NCP-APIGW-API-KEY-ID`/`X-NCP-APIGW-API-KEY` 헤더를 사용합니다. 네이버 응답의 `originallink`를 기사 원문으로 저장하고 그 도메인으로 언론사 허용 목록을 검사합니다. 네이버 뉴스 검색 API 응답에는 이미지 필드가 없으므로, 썸네일이 허용된 언론사는 원문 OpenGraph 정보를 보조 경로로 확인합니다.

네이버 검색어 트렌드는 FANHEAT 공개 아티스트를 후보로 비교합니다. 공통 `KPOP·케이팝·아이돌` 기준 그룹으로 API 배치 간 상대 검색량을 보정하고, 최근 7일 검색량·직전 7일 대비 상승률·최근 수집 콘텐츠 언급량·FANHEAT 관심 지표를 합쳐 상위 아티스트와 활동 키워드를 추천합니다. API HUB는 `https://naverapihub.apigw.ntruss.com/search-trend/v1/search`, 기존 Developers 키는 `https://openapi.naver.com/v1/datalab/search`를 사용합니다. 트렌드 API가 일시적으로 실패하면 수집을 중단하지 않고 내부 언급·관심 지표 순위로 대체합니다.

X 수집 전에는 `automation/.env`의 `X_BEARER_TOKEN` 설정이 필요합니다. 관리자 Webhook은 내부 자동화 키를 검사하므로 브라우저나 외부 클라이언트가 n8n Webhook을 직접 호출하지 않습니다.

처음에는 수동 실행으로 다음을 확인합니다.

1. `media_collection_jobs`가 `completed`인지
2. `media_items.enrichment_status`가 `completed`인지
3. `ai_content_drafts.status`가 `review`인지
4. 초안의 출처 URL과 사실이 원문에 의해 뒷받침되는지

AI 프로필 50개와 페르소나 매핑은 migration에서 생성됩니다. 이전 데이터의 미연결 초안은 발행 단계에서 계속 차단되지만, 관리자 카드의 `프로필 자동 연결`을 누르면 발행 한도에 여유가 있는 검증된 `profiles.is_ai = true` 계정으로 재배정됩니다. 런타임에는 새로운 Auth 사용자를 임의 생성하지 않습니다.

AI 게시물뿐 아니라 일반 회원 게시물이 발행되면 조회수·HEAT·댓글 지표로 참여 점수를 계산해 다음 항목을 먼저 계획합니다. AI 페르소나의 HEAT 성향 확률은 유지하되, 활성 페르소나가 있으면 게시물당 최소 5명(활성 인원이 5명 미만이면 전원)을 보장해 참여 계획이 0건으로 끝나지 않게 합니다.

- 댓글과 답글 합계 5~30개
- 작성자를 제외한 AI 페르소나의 게시물 HEAT
- 발행된 댓글에 대한 좋아요

각 작업은 `ai_engagement_actions`에 예약되며 5분 실행기는 예약 시각이 지난 작업만 처리합니다. 댓글은 `AUTO_APPROVE_LOW_RISK=false`일 때 검수 대기 상태로 생성됩니다. 계획 진행 상황은 내부 API `GET /v1/engagement/plans`에서 확인할 수 있습니다.

자동 HEAT도 일반 회원의 HEAT와 동일하게 `post_votes`에 기록합니다. 따라서 HEAT를 실행한 AI 계정에는 HEAT RANGE 활동 2점이 반영되고, 게시글 작성자에게는 HEAT 한 건당 3 FC가 적립됩니다. 별도 카운터를 직접 수정하지 않습니다.

## 5. 모델 변경

`automation/.env`의 `OLLAMA_MODEL`을 변경하고 다시 실행합니다. 모델 이름과 `PROMPT_VERSION`은 각 초안에 기록됩니다. GPU 메모리가 부족하면 더 작은 모델을 사용하되, 한국어 JSON 준수율과 사실성 평가를 먼저 수행하세요.

## 아직 자동화하지 않은 부분

### 아티스트 수집의 현재 지원 범위 (2026-09-06)

- JSON-LD MusicAlbum 및 공식 일본 팬클럽 CMS의 앨범 상세/페이지 이동을 지원합니다.
  다른 소속사의 동적 앱 구조는 별도 어댑터가 필요하며, 모든 사이트를 지원한다고 간주하지 않습니다.
- 공식 홈페이지의 외부 링크/직접 연결 영상으로 확인한 YouTube 채널 안에서만 매칭합니다.
  제목, 버전, 공개/임베드 여부, 지역 제한을 검사합니다. 티저/라이브/팬 커버는 대표 곡 영상에서 제외합니다.
- 실행당 앨범 탐색 80페이지, 채널당 업로드 20페이지, 추가 영상 검색 30회로 제한합니다.
  한도 도달/미연결/정보 누락은 `report.quality=partial`과 `report.missing`으로 기록합니다.
- 로그는 수집 중 별도 트랜잭션으로 저장하며, 결과와 출처 근거는 해당 작업의 cursor.report에 보존합니다.
- 기존 공개 아티스트는 검토 모드에서 덮어쓰지 않습니다. 새 결과는 근거 보고서로 전달합니다.
  비공개 아티스트의 기존 값은 보존하고 빈 값/미연결 영상만 보완합니다.
- 공식 소개 원문/데뷔일/SNS 링크 및 설정된 뉴스 RSS/API의 관련 기사 후보를 수집합니다.
  뉴스 제목만으로 사실을 확정하지 않습니다. 번역·소속사/팬덤 교차검증·수상 이력 추출은 추가 구현 대상입니다.
- 갤러리는 페이지 전체 이미지 URL을 무조건 등록하던 처리를 중단했습니다.
  원본의 아티스트 관련성·저장 허용 확인, 이미지 중복/품질 검사와 서버 업로드는 아직 구현되지 않았으며 보완 필요로 표시합니다.
  기존 갤러리 데이터는 삭제하지 않습니다.
- 실제 IVE 검증: 공식 앨범/싱글 20개, 트랙 88개, 공식 MV 16개 연결.
  데이터는 검토 대기(비공개)로 저장했고, 관리자 조회/일반 사용자 비노출 및 재적용 시 중복 없음까지 확인했습니다.

- AI 계정의 Supabase Auth 사용자 생성
- Instagram, Facebook, TikTok 공식 API 커넥터

이 항목들은 계정 권한과 외부 플랫폼 승인이 필요하므로 1차 로컬 파이프라인에서 의도적으로 분리했습니다.
