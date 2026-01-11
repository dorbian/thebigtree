# Changelog

## Unreleased
- FFXIV client: add cardgames host panel for creating sessions and copying join links.
- FFXIV client: add public cardgames URL setting for generated links.
- FFXIV client: add in-plugin host gameplay view with card images and actions.
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
