# FANHEAT Backend

Spring Boot 4.1.1과 Java 17 기반 API 서버입니다.

## 로컬 실행

DB 없이 API 골격만 실행:

```bash
mvn spring-boot:run
```

Supabase 연결 실행:

1. `.env.example`을 참고해 환경변수를 설정합니다.
2. `SPRING_PROFILES_ACTIVE=supabase mvn spring-boot:run`을 실행합니다.

지속 실행 서버는 Direct 연결을 권장합니다. 로컬 네트워크가 IPv4 전용이면 Supabase Dashboard의 Session pooler URL(5432)을 사용하세요.

- API 상태: `GET /api/health`
- DB 연결 상태: `GET /api/health/database` (`supabase` 프로필에서만 제공)
