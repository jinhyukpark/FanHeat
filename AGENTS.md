# FANHEAT engineering harness

These rules apply to every AI or human change in this repository. Treat this file as the operational contract for FANHEAT. When code and documentation disagree, inspect the running configuration before changing behavior and update the relevant documentation with the code.

## 1. System boundary and source of truth

FANHEAT has three operating surfaces. Do not assume that deploying one surface deploys the others.

1. **Public/admin web on AWS**
   - React/Vite source: `web/`
   - Production container: `compose.yaml`
   - Reverse proxy/static server: Caddy via `deploy/Caddyfile`
   - Deployment: `deploy/aws/deploy.sh`
   - Production URL: `https://fanheat.io`
2. **Local automation on the operator Mac**
   - Stack: `compose.automation.yaml`
   - Services: Collector API, Collector worker, Redis, AI Worker and n8n
   - Collector Studio: `http://localhost:8080/admin`
   - n8n: `http://localhost:5678`
   - AI Worker: `http://localhost:8090`
   - This stack is not deployed by the AWS web deployment script.
3. **Shared Supabase backend**
   - PostgreSQL, Auth, Storage and RLS are shared by the web and local automation services.
   - Database state is the source of truth for users, artists, posts, comments, votes, hero slides, collected media and AI drafts.
   - Do not replace a database-backed feature with hardcoded UI data. Fallback data may keep a page usable, but it must not be the only data shown in an administrator screen.

Primary configuration references:

- Web runtime: `compose.yaml`, `deploy/frontend.env`
- Local automation: `compose.automation.yaml`, `automation/.env`
- Automation behavior: `automation/README.md`, `automation/n8n/*.json`
- Database schema: `supabase/migrations/*.sql`

## 2. AWS deployment rules

- `deploy/aws/deploy.sh` deploys only `compose.yaml`, `web/`, `deploy/Caddyfile` and `deploy/frontend.env` to the EC2 host. It does not deploy n8n, Collector, Redis, AI Worker or Ollama.
- Use the existing deployment command from the repository root:

  ```bash
  AWS_REGION=ap-northeast-2 ./deploy/aws/deploy.sh
  ```

- Never create a second ad-hoc AWS deployment path when the existing script can be fixed or used.
- Before deployment, run `npm run build` in `web/` and preserve unrelated working-tree changes.
- If `aws` reports an expired session, run `aws login`, use `ap-northeast-2`, complete browser authentication and retry.
- SSH is restricted by an EC2 security-group `/32` rule. If the operator public IP changed, compare it with the existing rule before adding a new `/32`. Never open port 22 to `0.0.0.0/0`.
- A successful container replacement alone is not a completed deployment. Verify:

  ```bash
  curl -fsS https://fanheat.io/healthz
  curl -fsS https://fanheat.io/ | rg -o 'assets/index-[A-Za-z0-9_-]+\.js' | head -1
  ```

- Verify the remote `fanheat-web-1` container is running when deployment output is ambiguous.
- Do not use the raw EC2 IP for TLS verification; Caddy manages the certificate for `fanheat.io`.
- Keep the previous release recovery directory created by the deploy script. Do not delete it as routine cleanup.

## 3. Local automation and Ollama rules

- Start or rebuild local automation with:

  ```bash
  docker compose --env-file automation/.env -f compose.automation.yaml up -d --build
  ```

- The default AI Worker calls Mac-native Ollama at `http://host.docker.internal:11434`.
- The `ollama` and `ollama-pull` Docker services use the `container-ollama` profile and should remain stopped when Mac-native `ollama serve` is used. Do not run both modes without an explicit reason.
- Confirm the AI path with the Ollama API and AI Worker health. `llm_reachable` must be true before diagnosing generation quality.
- Redis is the Collector/Celery queue, not the content database. Restarting Redis must not be treated as resetting Supabase data.
- Rebuild only affected services where practical. A Collector UI/backend change normally requires `collector-api`; task execution changes may also require `collector-worker`; generation/publication changes require `ai-worker`.

## 4. n8n workflow rules

- Workflow JSON in `automation/n8n/` is version-controlled source. The n8n SQLite volume is runtime state.
- Every workflow has a fixed ID. Import over that ID; never create a duplicate workflow with the same purpose or schedule.
- Importing can deactivate a workflow. After import, explicitly set the intended active state and restart n8n.
- Required workflow state:
  - `FANHEAT admin full pipeline`: active
  - `FANHEAT Google Drive X import to AI drafts`: active
  - `FANHEAT publish approved AI content`: active
  - `FANHEAT AI comments and replies`: active
  - `FANHEAT artist profile import`: active
  - `FANHEAT scheduled artist refresh`: active
  - `FANHEAT scheduled YouTube collection to AI drafts`: inactive unless the product owner explicitly re-enables unattended collection
- After changing workflows, verify `n8n list:workflow --active=true` and confirm no duplicate scheduled publisher or collector exists.
- Webhooks and internal service calls must validate `FANHEAT_INTERNAL_API_KEY`. Never put database passwords, service-role keys or provider secrets in workflow JSON.

## 5. Collection, AI approval and publishing contract

The difference between the two Collector Studio actions is a safety boundary.

- **수집만 실행**
  - Collect and deduplicate external media only.
  - Do not generate AI drafts, approve content, schedule posts or publish posts.
- **전체 자동화 실행**
  - Runs collection → analysis → draft generation.
  - Drafts created by this explicit action must carry `trigger_source = 'admin_full_automation'`.
  - Only low-risk drafts satisfying the configured confidence policy may receive `approval_source = 'auto_policy'`.
  - Eligible posts are scheduled at the configured non-uniform interval and published when due.
- The background publisher may process only administrator-approved drafts or policy-approved drafts whose `trigger_source` is `admin_full_automation`.
- A server restart, n8n schedule, plain collection job or historical `auto_policy` draft must not silently become authorization to publish.
- Explicit “publish now” actions may publish selected approved drafts immediately, but must enforce profile linkage, state and daily limits.
- Risk flags, source attribution and original links must survive every pipeline stage.

## 6. External content and media rules

- Prefer official APIs, RSS, oEmbed or platform embed mechanisms. Respect provider terms, access tiers and rate limits.
- TikTok keyword discovery uses Naver web search and official TikTok oEmbed. Never scrape TikTok search. oEmbed success is not proof of playback or redistribution rights; discovery time is not publication time. Research API code is dormant and requires approval before use.
- Do not imply that an official artist page grants blanket permission to copy its images.
- News images are remote link previews, not owned FANHEAT assets. Do not download or copy them into FANHEAT Storage unless rights and product requirements explicitly allow it.
- Only use a news thumbnail when publisher configuration permits RSS/API/OpenGraph preview use. Preserve the publisher label and original article URL.
- YouTube, TikTok, Instagram, Facebook and X embeds must use each platform's supported public/embed mechanism. A visible public post is not equivalent to API or redistribution permission.
- Validate all external URLs as public HTTPS URLs and retain SSRF protections and redirect-domain checks.
- AI-generated summaries must be original writing grounded in the source. Do not reproduce full news articles or long copyrighted passages.

## 7. Naver recommendation rules

- Naver Search Trend does not discover popular keywords. It compares candidate keyword groups supplied by FANHEAT.
- When FANHEAT has eligible public artists, use them as candidates and combine Naver trend, recent media mentions and FANHEAT interest signals.
- When no eligible artist exists, `다시 찾아보기` may discover conservative candidate names from recent Naver K-POP news headlines, then rank those candidates with Search Trend.
- Forced refresh must bypass the six-hour in-process cache and visibly report loading, empty, fallback and error states.
- Do not present headline extraction as verified artist identity. Discovered terms are collection keywords until matched to a reviewed FANHEAT artist.

## 8. Supabase and database rules

- Create schema changes with `supabase migration new <descriptive-name>`; do not invent migration timestamps manually.
- Inspect current CLI help before using migration, query or advisor commands.
- Never expose `service_role`, database credentials or secret API keys in React, public environment variables, logs or screenshots.
- Enable RLS on every new table in an exposed schema. Public read and administrator write policies must be separate and minimal.
- Administrator authorization must use trusted app metadata or the existing `public.is_admin()` mechanism, never user-editable metadata.
- Verify both admin and non-admin behavior after administrator changes. PostgreSQL RLS updates also require a matching select policy.
- Run the Supabase security advisor after RLS, Auth, Storage, view, function or administrator changes. Report pre-existing unrelated warnings separately.
- Run a real test query after applying a database change. A migration file without verification is incomplete.
- Seed and recovery migrations must be idempotent and must not overwrite administrator-managed production data. Prefer inserting defaults only when the target table is empty or when a stable unique key is missing.

## 9. Desktop and mobile product rules

- Desktop and mobile use the same data and actions but may have different composition. Do not fork business logic or create mobile-only copies of persisted data.
- Treat mobile as a deliberate layout, not a scaled-down desktop screenshot:
  - reflow controls and lists;
  - keep primary actions reachable;
  - avoid horizontal page overflow;
  - keep fixed bottom navigation from covering content;
  - test dialogs, keyboards, safe areas and long Korean labels.
- Desktop must preserve the left ranking/vote panel, central content hierarchy and right-side/detail behavior without forcing mobile widths or touch-only interactions.
- Navigation, authentication, vote state, filters, counts and administrator changes must produce the same underlying result on desktop and mobile.
- For responsive changes, inspect at least one desktop width, one tablet width and a mobile width near `390px`.

## 10. UI typography and readability

- Do not introduce visible UI text smaller than `12px`. Icon-only glyphs, decorative logos and hidden accessibility text are the only exceptions.
- Use the shared FANHEAT scale: caption `12px`, metadata `13px`, body/control `14px`, card title `16px`, section title `20px` or larger.
- Mobile layouts must not reduce body, metadata, labels or actions below the desktop minimum. Reflow or hide nonessential content instead of shrinking it.
- Match new list and form typography to the main feed and writer. Dense layouts are not permission to use unreadable text.
- For the my-page left profile panel and POST / BOOKMARK / FRIENDS / COMMENT panel, make changes in `web/src/my-page-readable.css`. Keep it imported last in `web/src/main.jsx` so legacy styles cannot silently shrink text.
- Never encode user-facing copy or numeric values in CSS `content`; render meaningful data in JSX/HTML.
- Interactive controls require visible focus states, useful accessible names and disabled/loading feedback.

## 11. Product priorities

Preserve these priorities in order when trade-offs are required:

1. No unauthorized publication or destructive loss of user/admin data.
2. Clear provenance, source attribution and media-rights boundaries.
3. Consistent database-backed behavior across public web, admin web and local automation.
4. Readable, responsive mobile and desktop experiences.
5. Recoverable operations, observable job state and actionable errors.
6. Performance improvements that do not weaken correctness, security or attribution.

Do not hide an empty/error state with convincing hardcoded production data. Fallback visuals must be distinguishable in code, while administrator tools must expose and repair persisted state.

## 12. Required verification matrix

- **Any React/CSS/frontend change**
  - Run `npm run build` in `web/`; the typography harness must pass.
  - Inspect desktop and mobile behavior relevant to the change.
- **My-page UI**
  - Verify headings, body text, metadata, button labels, empty states and modal copy on desktop and mobile.
- **Collector change**
  - Run `python -m compileall` for Collector source and affected `services/media-collector/tests`.
  - Rebuild the affected local container and verify the real authenticated endpoint or UI.
- **AI Worker/publication change**
  - Run `services/ai-worker/tests`.
  - Verify AI Worker health and `llm_reachable`.
  - For publishing changes, test provenance/approval filters, not only successful insertion.
- **n8n change**
  - Parse workflow JSON, import by fixed ID, restore intended active state, restart n8n and list active workflows.
- **Supabase change**
  - Verify applied schema/data with a real query.
  - Test appropriate anon, authenticated and admin access paths.
  - Run the security advisor when required.
- **AWS deployment**
  - Verify `https://fanheat.io/healthz`, the current hashed bundle and remote container status.

If a full suite cannot run because an image lacks Node, browser dependencies or another tool, run the focused relevant suite and report the environmental limitation precisely. Do not describe an unexecuted test as passing.

## 13. Change discipline

- Preserve unrelated dirty working-tree changes. Never reset, clean or overwrite them to simplify a task.
- Use `rg` for repository searches and `apply_patch` for manual file edits.
- Do not delete production data to repair a display problem. Diagnose missing rows, RLS, cache, fallback behavior and deployment drift first.
- Avoid duplicate systems: one canonical table, one workflow purpose, one deployment script and one responsive business flow.
- Keep visible copy in Korean where the surrounding product is Korean; keep code identifiers and operational commands clear and consistent.
- Update this harness whenever architecture, deployment boundaries, workflow activation policy or core product safety rules change.
