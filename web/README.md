# FANHEAT Web

React 19 + Vite 기반 FANHEAT 웹 프로젝트입니다. 사용자 화면, `/admin` 관리자 화면, 개인정보 처리방침과 약관 페이지를 모두 포함하며 Supabase에 직접 연결합니다.

```bash
npm install
npm run dev
```

- 사용자 화면: `http://localhost:5173/`
- 관리자 화면: `http://localhost:5173/admin`
- 개인정보 처리방침: `http://localhost:5173/legal/privacy`

관리자 계정은 Supabase Auth 계정이어야 하며 안전한 `app_metadata.role=admin` 권한이 필요합니다. 브라우저에는 publishable key만 사용하고 service role key를 넣지 않습니다.

## 카카오 로그인 설정

사용자 로그인 모달은 Supabase Auth의 `kakao` OAuth 제공자를 사용합니다. 운영 활성화에는 다음 설정이 필요합니다.

1. Kakao Developers에서 앱을 만들고 **REST API 키**와 활성화된 **카카오 로그인 Client Secret**을 준비합니다.
2. Kakao Developers의 카카오 로그인 Redirect URI에 아래 Supabase 콜백을 등록합니다.

   ```text
   https://yuiemljibxeoifupvluc.supabase.co/auth/v1/callback
   ```

3. 카카오 로그인 동의 항목에서 `profile_nickname`, `profile_image`를 설정합니다. 이메일을 사용할 경우 비즈 앱 전환 후 `account_email`도 설정합니다.
4. Supabase Dashboard의 **Authentication → Sign In / Providers → Kakao**에서 REST API 키를 Client ID로, Client Secret을 Client Secret으로 입력하고 제공자를 활성화합니다.
5. 이메일 동의를 받지 않는 구성이라면 Supabase Kakao 제공자의 **Allow users without an email**도 활성화합니다.
6. Supabase URL Configuration의 Redirect URLs에 개발용 `http://localhost:5173/`와 운영용 `https://fanheat.io/`를 등록합니다.

Client Secret은 프런트엔드 환경 변수나 Git에 저장하지 않습니다. 로컬 Supabase Auth로 OAuth를 검증할 때만 `supabase/config.toml`의 예시 블록을 활성화하고 루트 `.env`에 `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`을 둡니다.

프로덕션 빌드는 `npm run build`로 확인할 수 있습니다.
