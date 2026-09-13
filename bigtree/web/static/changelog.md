# Changelog

## 2026-09-11
- Cardgames: serialize and row-lock state mutations, commit state + event publication atomically, and reduce live SSE/WebSocket polling to one database query per tick.
- Cardgames: fix Blackjack split-hand advancement, reject duplicate Craps round rolls, throttle finished-session cleanup, and rely on PostgreSQL cascade cleanup.
- Wallets: make first-use balance changes row-safe and add idempotent per-game debit/payout keys with compensating refunds when a game reducer fails.
- Web: move the bulk Elfministration CSS/handlers out of the HTML shell, precompress cacheable static assets at image-build time, and serve gzip without spending Pi CPU per request.
- Web security: trust forwarded HTTPS/client-IP headers only from configured/private proxy networks, add baseline browser hardening/no-store headers, and include X-Cardgame-Token in CORS preflight support.
- Deployment: use a multi-stage slim runtime container, cancel superseded GitHub builds, and expose the source commit SHA through health/readiness responses for rollout traceability.
- Runtime: make container stdout the default diagnostic log path and recover optional rotating logs from stale/closed file descriptors.
- Runtime: add graceful worker/web/database/logging shutdown plus `/healthz` and Discord/PostgreSQL-aware `/readyz`.
- Database: use a small bounded PostgreSQL connection pool suited to the Raspberry Pi deployment and add transaction support for atomic operations.
- Plogon: use conditional requests/content checks and stop rewriting `/data/with.leaf` when the source has not changed.
- Conclave: add Verdant Conclave, a Discord-channel-bound elf social-deduction game with persistent PostgreSQL state, private roles/actions, nominations, trials, judgements, last wills and deliberate pass/abstain choices.
- Conclave: add host-safe web and Forest controls without revealing living secret roles.
- Web: add responsive workspace navigation, Conclave host guidance, connection state, mobile drawer navigation, and a forest-themed embedded admin dashboard.
- Web: convert bundled multi-megabyte backgrounds to compact WebP assets and preload the active shell background.
- Media: generate WebP thumbnails and screen-sized previews for uploaded images, lazy-load/decode gallery images, progressively render large media grids, and validate oversized/damaged raster uploads before decoding.
- Web: defer panel-specific Tarot/Bingo/dashboard work until it is actually needed and prefer the local changelog before the GitHub fallback.
- Auth: establish same-origin HttpOnly browser sessions for embedded administration instead of placing the active admin token in iframe query strings.
- Correctness: make one-use temporary links and gallery reactions atomic, remove the duplicate media migration implementation, and harden Bingo/Hunt local state writes.
- UI: fix the existing Tarot calendar preview DOM bug and remove the recursive/duplicated Auth Logins dashboard iframe.
- CI: run Python tests/compile checks before container publication and add Go validation to the overlay-client workflow.

## Unreleased
- Wallet: show event wallet balances as amount + currency and clean up the event list columns.
- Wallet: improve bingo player links by falling back to the owner name when tokens are missing.
- Gallery: render text-only inspiration entries without images, artists, or watermarks.
- Wallet: refine game list fields (paid amount, title-first, date-only), add bingo player links, and improve event return links.
- Events: add public event games listing and show wallet balance + open tables on the event page.
- Gallery: add configurable layout/inspiration settings and randomize inspiration text.
- Overlay: add casino menu placeholders, gallery layout controls, and wallet top-up comments/carry-over.
- Wallet: enforce custom-currency balances on cardgame joins and credit winnings on finish.
- Events: log wallet activity (top-ups, joins, wins), show it in wallet event details, and add house total summary.
- Overlay: add plugin setup panel and refine games list pagination layout.
- Overlay: allow event wallet top-ups by host and store /auth users for admin selection.
- Wallet: show larger user pill and store XivAuth world on login.
- Wallet: show active/past events alongside games and add event details modal.
- Events: show registered players list in overlay event modal.
- Overlay: support admin login background via `system_configs.overlay.admin_background`.
- Wallet: claim join codes now seeds cardgames/tarot/bingo sessions when missing in Postgres.
- Overlay: add bingo owner link copy button beside player rows.
- Gallery: wallet badge uses icon + username when logged in.
- Player pages: show logged-in wallet user and allow assigning sessions to the user.
- Wallet: add player-page links for tarot/cardgames sessions and hide gallery redirects.
- Gallery: show logged-in wallet name on the front page.
- User area: add join-key claim box, game history table, and player-friendly details modal.
- User area: show logged-in character name in header and streamline login controls.
- User area: map XIVAuth /characters response to xiv_username during login.
- XivAuth: added OAuth state secret support for multi-pod logins.
- XivAuth: added token header/prefix config for OAuth verify calls.
- Overlay: restored missing bingo/cardgames/tarot admin loaders after log viewer update.
- Dashboard: added log viewer for boot/auth/upload logs and moved artist index to user management.
- Database: retry JSON/deck imports when empty and log migration paths.
- Dashboard: grouped admin actions into user/media/config/access sections and restored gallery/media controls.
- Gallery: wallet icon now starts XivAuth login and returns to user-area.
- User area: added XivAuth OAuth login button and callback flow for user-area sessions.
- Overlay: added XivAuth OAuth fields to system config UI.
- User area: added XivAuth OAuth configuration keys (client_id/secret, authorize_url, token_url, scope, redirect_url).
- FFXIV client: add cardgames host panel for creating sessions and copying join links.
- FFXIV client: add public cardgames URL setting for generated links.
- FFXIV client: add in-plugin host gameplay view with card images and actions.
- Cardgames: add customizable currency and persist cardgame defaults in overlay/FFXIV.
- FFXIV client: fix cardgames live view label rendering.
- FFXIV client: guard card texture rendering to avoid null crashes.
- FFXIV client: include priestess token in generated host links.
- FFXIV client: allow background URL and clone-from-selected for cardgames.
- FFXIV client: guard card list rendering against transient JSON state errors.
- FFXIV client: add Sessions/Games/Players layout with categorized game cards and sessions list.
- Added delete session for cardgames and background image selection in the dashboard.
- Cardgame host/player pages now render the session background.
- Added dashboard changelog panel and refreshed dashboard content.
- Added retry/backoff for /permissions registration on startup.
- Cardgame sessions: dynamic polling fallback, card centering, larger cards, and artist credits.
- Blackjack: dealer back image for hidden card, dealer totals/lead on host view, and host-only finish.
- Cardgames: sessions now stay alive until host finishes; no player auto-end.
- Poker: converted to 1v1 Texas Hold'em with host-controlled stage advance.
- High/Low: added decision-focused UI (double/stop, intent/settlement preview) and synced winnings/state flow.
- Cardgame sessions: open media library now always opens the panel before scope checks.
- Media library: guard against non-JSON responses and surface clearer errors.
- Gallery: strip emoji characters from Discord-sourced image titles.
- Gallery: add inline fallback handler for Join game prompt.
- Overlay: always show delete session action outside icon groups.
- Gallery: generate thumbs for contest media and use media thumbs for tarot when local.
- Gallery: enable virtualization by default and reduce initial batch size.
- Gallery: reduce initial batch to 20 and warm thumbs for first items.
- Cardgames: background picker now opens the media library modal.
- Poker (host view): hide player hand with face-down placeholders.
- Poker (host view): use deck back image for hidden player cards.
- Poker (player view): show dealer hand alongside player, with card backs until reveal.
- Dashboard: move changelog to top, restore thank you section, and fetch changelog from GitHub with fallback.
- Poker: reveal hands at showdown or finished state for player + host views, with side-by-side layout on host.
- Dashboard: table of contents updated to include thank you section.
- Cardgames: show background artist credit in-game with modal details.
- Gallery: added Join game button that routes join codes to the right session page.
- High/Low: host can play actions and action errors now surface in the UI; hide empty artist credits.
- Poker: added round-based betting UI with staged community reveal and action tracking.

## 2026-01-11
### Cardgames
- Added Cardgame Sessions panel with host/player links, start/finish, and session cloning.
- Added cardgame API endpoints plus session storage in SQLite.
- Cardgames now use tarot decks as playing cards with suit/rank parsing.
- Expanded auth scopes so cardgames can read tarot decks.

### Rites starting page
- Added rites starting splash page (nginx pod) with heart animation and redirect probe.
- Added quadlet for auto-starting the splash container.

### Gallery
- Tweaked gallery navigation and link targets for rites.

### Infrastructure
- Cardgames parser and lock handling adjustments to reduce contention.
