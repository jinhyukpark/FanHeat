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

프로덕션 빌드는 `npm run build`로 확인할 수 있습니다.
