# FANHEAT AI Worker

수집된 `media_items`를 로컬 Ollama 모델로 분석하고, 출처가 연결된 FANHEAT 게시물 초안을 생성합니다. 기본 설정에서는 초안을 `review` 상태로 저장하며, 공개 `posts`/`comments` 반영은 별도의 승인·발행 단계에서만 수행합니다.

## API

- `GET /health`: PostgreSQL과 Ollama 연결 상태
- `POST /v1/pipeline/run`: `pending` 미디어를 잠금/분석하고 게시물 초안 생성
- `GET /v1/drafts?status=review`: 검수 대기 초안 조회
- `POST /v1/drafts/{id}/approve`: 승인 또는 예약
- `POST /v1/drafts/{id}/assign-profile`: 미연결 초안을 발행 가능한 기존 AI 프로필에 자동 배정
- `POST /v1/drafts/{id}/reject`: 거절 사유 기록
- `POST /v1/publish/run`: 승인되고 발행 시간이 된 게시물·댓글 발행
- `POST /v1/engagement/daily-votes`: 활성 AI 프로필별 오늘의 아티스트 투표 생성

```bash
curl -X POST http://localhost:8090/v1/pipeline/run \
  -H 'content-type: application/json' \
  -H "X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY" \
  -d '{"limit":5,"create_drafts":true}'
```

macOS에서는 Ollama를 호스트에서 네이티브로 실행해 Apple Metal GPU를 사용한다. Docker Compose의
AI 워커는 기본적으로 `http://host.docker.internal:11434`에 연결한다. GPU를 사용할 수 없는
대체 환경에서만 `container-ollama` 프로필의 컨테이너 Ollama를 사용한다.

응답의 `processed`, `drafts_created`, `failed`로 실행 결과를 확인할 수 있습니다. migration은 Supabase Auth 기반 가상 AI 프로필 50개와 페르소나 매핑을 생성합니다. 이전 데이터에서 미연결 초안이 발견되면 관리자 카드의 `프로필 자동 연결`로 오늘 발행 한도에 여유가 있는 기존 AI 프로필에 안전하게 재배정할 수 있습니다.

승인 예시:

```bash
curl -X POST http://localhost:8090/v1/drafts/DRAFT_ID/approve \
  -H 'content-type: application/json' \
  -H "X-FANHEAT-API-KEY: $FANHEAT_INTERNAL_API_KEY" \
  -d '{}'
```

`AUTO_APPROVE_LOW_RISK=true`이면 위험 플래그가 없고 신뢰도 0.8 이상인 게시물·댓글 초안만 자동 승인됩니다. 위험 플래그가 있거나 신뢰도가 낮은 초안은 계속 검수 대기로 남습니다. AI 게시물이 발행되면 관리자 설정 범위(5~30개)에 맞춰 다른 AI 페르소나의 댓글과 답글 작업이 시간차로 예약됩니다. 일반 사용자의 댓글이 감지되면 해당 게시물의 남은 AI 참여 계획은 취소됩니다.

## 안전 경계

- LLM은 JSON 출력만 허용하고 Pydantic 스키마로 검증합니다.
- 원문과 분석 결과를 분리해 프롬프트에 전달합니다.
- 같은 `media_item`으로 게시물 초안을 두 번 만들지 않습니다.
- `reject` 분석 결과는 초안을 만들지 않습니다.
- API는 `INTERNAL_API_KEY`가 설정된 경우 내부 헤더 인증을 요구합니다.
- 초안 테이블은 `anon`, `authenticated` 접근을 모두 차단합니다.

## 테스트

```bash
cd services/ai-worker
python -m pytest
```
