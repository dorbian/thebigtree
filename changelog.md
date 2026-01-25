# Changelog

## Unreleased
- Overlay: add a subtle tint overlay in overlay mode to reduce background vibrancy.
- Overlay: darken admin background overlays on login and admin shell.
- Overlay: guard cardgame session UI bindings when elements are absent and fix the missing brace.
- Overlay: bust overlay CSS + admin background cache in local dev.
- Overlay: drive admin background from a CSS variable for both login and app shell.
- Overlay: split login vs. app-shell background URLs to keep the logged-in view on adminlogin.png.
- Dev: disable caching for HTML/CSS/JS in the frontend dev server.
- Overlay: let login screen use shared overlay variables for darkness.
- Overlay: add an extra darkening layer over the logged-in shell background.
- Overlay: set logged-in shell darkening layer to 50%.
- Overlay: darken dashboard admin cards for readability.
- Overlay: reduce transparency on dashboard KPI and admin cards.
- Overlay: match dashboard card backgrounds to KPI opacity for readability.
- Bingo: show the sessions list inside the bingo panel.
- Dev: proxy binary API responses without UTF-8 decode errors.
- Bingo: prefill create modal currency and background from venue defaults.
- Bingo: simplify session overview list to title-only selections.
- Bingo: hide bingo controls until a session is selected.
- Bingo: move sessions list into its own panel and switch to details on selection.
- Bingo: use normal-width buttons and route status messages to the sidebar.
- Bingo: move buy cards controls to players header and remove admin tools panel.
- Bingo: remove the inline status field from the bingo panel.
- Bingo: tighten player list rows to single-line height.
- Bingo: default to the sessions list on load when bingo access is available.
- Bingo: remove the Advanced section from the bingo panel.
- Bingo: remove visible Game ID and seed pot controls from the bingo panel.
- Bingo: fall back to the sessions list when no game is selected on refresh.
- Wallet: ensure the wallet/event background scales to the viewport.
- Cardgames: open player/host views in the overlay iframe instead of new tabs.
- Cardgames: guard missing cardgame form fields to avoid null errors.
- Cardgames: guard missing deck select when applying session details.
- Cardgames: allow open player/host when the game selector is missing.
- Dev: proxy /cardgames routes in the frontend dev server.
- Dev: proxy /contests root in the frontend dev server.
- Bingo/Cardgames: add event selection to creation and store event metadata on create.
- Overlay: guard missing bingo refresh control binding.
- Overlay: prevent deck editor horizontal overflow.
- Tarot: add template card API with tarot/playing templates and deck purpose metadata.
- Overlay: add deck purpose controls and template card picker for new card creation.
- Bingo: upsert new games into the games list for the admin archive.
- Overlay: move deck editor save button to the top deck controls row.
- Wallet: classify active vs past games using status when available.
- Overlay: neutralize login background hue and reduce panel/card opacity.
- Overlay: apply adminlogin.png background after login across the admin shell.
- Overlay: rename UI labels to Elfministration.
- Gallery: tighten sidebar width and make left actions use natural button sizing.
- Gallery: restyle sidebar icon links as buttons and tighten layout padding to avoid overflow.
- Gallery: add modal voting panel, fix right-column layout, and theme scrollbars.
- Updater: use logger instead of missing logging.print to avoid startup crash.
- Media library: drive /api/media/list, uploads, and updates from Postgres instead of media.json.
- Gallery: import artist names/links from legacy media.json into Postgres media_items.
- Gallery: resolve artist names from legacy media metadata when artist_name is missing.
- Gallery: fix stray top-level return that broke gallery.js initialization.
- Bingo: fix missing get_database import when searching owners during game creation.
- Database: ensure discord_users columns exist before querying user names.
- Overlay: show cardgames session-create status/errors when scopes are missing or the API fails.
- Auth: resolve /api/auth/me tokens via DB-first lookup with web_tokens.json fallback.
- Overlay: send auth token via storage fallback and Authorization header for API requests.
- Overlay: guard missing overlay toggle elements when loading settings or clearing auth.
- Database: remove legacy system_configs payload access and use data column consistently.
- Wallet: treat bingo join codes that match the game id as owner links for player pages.
- Overlay: add XivAuth selector + link action to bingo owners list and surface linked users.
- Frontend: move wallet and bingo card/owner scripts/styles into static assets.
- Overlay: separate sidebar/content scrolling for large admin panels.
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
- Venues: store Discord admin venue memberships separately to avoid integer overflow.
- Cardgames: switch SQLite to WAL and reduce connect timeouts to prevent session-create stalls.
- Cardgames: migrate session/event storage to Postgres and drop SQLite dependency.
- Cardgames: switch host/player session updates to WebSockets with resume + idle timeout.
- Events: allow guest users via per-event cookies for joining/creating tables without XIVAuth.
- Events: add guest wallet top-ups for event-only balances.
- Events: support join wallet credits configured at event creation.
- Gallery: escape origin/title/artist fields so flair text renders as text.
- Dashboard: add Gallery admin card with media/calendar/flair actions.
- Venues: add delete controls in the admin list and normalize refresh button size.
- Games list: auto-trigger JSON migration when empty to repopulate.
- Wallet: remove join-key label and align user pill sizing with header actions.
- Wallet: combine event wallet balance with currency, make history scrollable, and keep event games inside event details with player links.
- Cardgames: hide artist panel when no card credits and avoid defaulting background credits to Forest.
- Events: allow event-created blackjack sessions to restart rounds from the player view.
- Media: allow hidden-on-upload in the media library and improve upload error handling for non-JSON responses.
- Uploads: increase server and gateway upload size limits to avoid 413 errors.
- Backend: add Postgres persistence with JSON migration, deck import, and a first-pass user area backed by XivAuth login.
- Backend: persist XIVAuth/OpenAI config in Postgres, import the INI defaults on first run, and expose a management API plus overlay UI to edit those settings.
- Frontend: add wallet login trigger, user-area experience, and game-management view plus textual flair badges.
- Frontend: overlay now links to the XivAuth management page and the wallet includes setup guidance; plogonmaster.json refreshes hourly when available.
- Backend: download `plogon.json` into the data directory (`with.leaf`) and serve it from there.
- Cardgames: finish now archives sessions instead of deleting them.
- FFXIV client: unify cardgame host panel layout and padding across blackjack/poker/highlow.
- FFXIV client: add blackjack start/end and clone+end controls in the host view.
- Cardgames: allow host actions for blackjack (hit/stand/double/split) in the FFXIV client.
- Cardgames: add draft session creation flag and draft-aware start handling.
- Blackjack: support split/double actions with multi-hand state and payouts.
- FFXIV client: move cardgame setup into a prepare popup with deck refresh and draft creation, plus updated session header and actions.
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
- FFXIV client: refresh Forest Manager layout with party-planner game categories, share controls, and a sliding control surface.
- FFXIV client: polish Forest Manager Games cards with themed headers, accents, and badge chips.
- FFXIV client: rebuild Games view into large colored section blocks with consistent button sizing.
- FFXIV client: add resizable main split and right panel collapse toggle.
- FFXIV client: add session close actions and throttled auto-refresh for sessions list.
- FFXIV client: refine Games view spacing, badge wrapping, and panel resize behavior.
- FFXIV client: return Bingo to party games and add extra panel padding.
- FFXIV client: replace sessions list icons with ASCII markers and adjust game card padding.
- FFXIV client: add badge tooltips for game requirements.
- FFXIV client: keep ASCII session icons and centered layout without external fonts.
- FFXIV client: restore Font Awesome asset and use UiBuilder.IconFont when available.
- FFXIV client: retry icon font init and support ImGuiNET IconFont bindings for Font Awesome.
- FFXIV client: add glossy 3D primary buttons for Prepare session and Start.
- FFXIV client: increase game section/card padding and add header icons with fallbacks.
- FFXIV client: remember right pane state after starting games and move Games/Settings controls into sessions list header.
- FFXIV client: apply initial right pane collapsed sizing on first draw.
- FFXIV client: slightly widen collapsed window width.
- FFXIV client: increase game card left padding and push action buttons further right.
- FFXIV client: allow Games header button to toggle closed and align draw header icon with sessions list.
- FFXIV client: remove category suffix from game cards and align section descriptions under titles.
- FFXIV client: remove obsolete top menu bar from Forest Manager.
- FFXIV client: only track nearby players when a session provides a roster (reduces idle scanning).
- FFXIV client: restore nearby list when no roster is active; filter only when roster exists.
- FFXIV client: switch players/sessions refresh controls to icon buttons.
- FFXIV client: refresh nearby list only on open/area change/manual refresh, with accented refresh buttons.
- FFXIV client: move sessions permissions status to footer with connection dot.
- FFXIV client: add setting to disable nearby player scanning to reduce lag.
- FFXIV client: make nearby player scanning manual (scan button + area change) and move permissions status to a separate footer panel.
- FFXIV client: stop permissions polling after failures until the API key changes.
- FFXIV client: avoid permission polling when no API key is set and start disconnected on launch.
- FFXIV client: align permissions footer height and match session close button background to row.
- FFXIV client: separate sessions footer from list scroll and restore game card left padding.
- FFXIV client: tweak scan icon, footer height, and title/description alignment in Games.
- FFXIV client: store game creation defaults per character and pad the permissions footer.
- FFXIV client: tighten sessions/footer layout and prevent permissions text clipping.
- FFXIV client: show disconnected state in permissions footer with a 3D red indicator.
- FFXIV client: add settings button to delete all local plugin data with confirmation.
- FFXIV client: rename cardgames public URL setting to Server and normalize https input.
- FFXIV client: update Bingo admin default base URL to rites.thebigtree.life.
- FFXIV client: update default/fallback Bingo API base URL to rites.thebigtree.life.
- FFXIV client: split game card title and detail padding to tune alignment.
- FFXIV client: load per-character defaults after login to avoid off-thread LocalPlayer access.
- FFXIV client: add Defaults popup for game creation settings next to Games.
- API: add auth permissions endpoint for clients to query allowed scopes.
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
## 2026-01-16
### Overlay
- Guarded DOM event bindings to avoid crashes when nodes are missing.
- Fix syntax error in overlay menu bindings.
- Fix stray brace in contest status block.
- Fix extra brace in gallery import handler.
- Trim dashboard content and add a changelog toggle button.
- Accept scope data from string or array to restore menu visibility.
- Persist overlay API key in session storage as a fallback for refreshes.
- Restore bingo menu bindings and payload preview logic.
- Guard overlay toggle bindings when controls are missing.
### Auth
- Return resolved scopes from `/api/auth/me` for API keys and deny invalid tokens.
## 2026-01-20
### Gallery
- Replaced right-column suggestions with a configurable messages panel.
- Added message title/body fields to gallery settings and overlay layout controls.
- Removed cards-per-row control from gallery layout to keep layout feed-based.
- Centered in-image details, aligned admin/discord buttons, and limited modal open to image clicks.
- Adjusted modal layout to place details above the artwork.
- Restored gallery scroll behavior and resized images to fill the feed column.
- Moved gallery announcements into the left menu and switched to a two-column layout.
- Updated gallery modal to place details below the artwork and darken the overlay.
- Styled modal details as a fixed-width gallery card under the image.
- Locked modal details to the selected image and refreshed vote counts in-modal.

### Overlay
- Added elfministration routes (with redirects from legacy overlay routes).
- Updated gallery import UI copy and button labeling.
- Simplified plugin setup with copyable link card in dashboard.
- Stacked dashboard action buttons vertically and moved log selection into a modal card.
- Matched plugin setup and logs panels to the dashboard card grid.
- Moved log output and refresh into the logs modal, with log type selection on the card.
- Softened panel backgrounds and reduced non-dashboard panel width.
- Updated overlay button styling to match dashboard buttons across panels.
- Require admin venue assignment on login and attach venues to events/games.
- Auto-create always-open slots/blackjack sessions for active events and close them when events end.

### UI
- Switched all site typography to sans-serif for consistency across pages.
## 2026-01-23
### Cardgames
- Rebuilt slots player view as a 3x3 grid and cleaned up corrupted markup.
- Enforced wallet auth headers and redirect handling for player actions.
- Normalized cardgame player templates to ASCII-only symbols and text.
- Redirect players to the gallery when wallet balances hit zero after actions.
- Mark deleted cardgame sessions as inactive in the games table.
### Media
- Added media type and venue filtering for the admin media gallery.
- Stored media type and venue metadata on upload/edit to support filtering.
### Venues
- Added per-game background overrides for venue defaults (slots/blackjack/poker/highlow/crapslite).
### Events
- Simplified event join page to show create/open per game and avoid duplicate wallet balance text.
### Cardgames
- Show wallet balance in player headers and include it in state polling.
