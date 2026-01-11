# Changelog

## Unreleased
- Added delete session for cardgames and background image selection in the dashboard.
- Cardgame host/player pages now render the session background.

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
