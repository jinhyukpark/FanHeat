# FANHEAT agent harness

These rules apply to every AI or human change in this repository.

## UI typography and readability

- Do not introduce visible UI text smaller than `12px`. Icon-only glyphs, decorative logos, and hidden accessibility text are the only exceptions.
- Use the shared FANHEAT scale: caption `12px`, metadata `13px`, body/control `14px`, card title `16px`, section title `20px` or larger.
- Mobile layouts must not reduce body, metadata, labels, or actions below the desktop minimum. Reflow or hide nonessential content instead of shrinking it.
- Match new list and form typography to the main feed and writer. Dense layouts are not permission to use unreadable text.
- For the my-page left profile panel and POST / BOOKMARK / FRIENDS / COMMENT panel, make changes in `web/src/my-page-readable.css`. Keep it imported last in `web/src/main.jsx` so legacy styles cannot silently shrink text.
- Never encode user-facing copy or numeric values in CSS `content`; render meaningful data in JSX/HTML.

## Required verification

- Run `npm run build` in `web/` after frontend changes. The build includes the typography harness and must pass.
- When changing my-page UI, verify both desktop and mobile rules and inspect headings, body text, metadata, button labels, empty states, and modal copy.
- When changing Supabase administrator features, verify both admin and non-admin RLS behavior and run the Supabase security advisor.
