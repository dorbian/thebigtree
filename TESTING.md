# Testing BigTree Frontend Locally

## Quick Start (With Remote API)

### Option 1: Frontend Server (Recommended for Frontend Testing)
This serves only the UI and proxies API calls to a remote server.

```bash
# Edit dev_frontend.py and change REMOTE_API_URL to your API server
# Then run:
run_frontend_server.bat
```

**Opens at:** http://localhost:3001/elfministration

Edit `dev_frontend.py` to point to your API server:
```python
REMOTE_API_URL = "http://your-api-server.com:8443"
```

### Option 2: Full Local Stack (Requires PostgreSQL)
If you have PostgreSQL running locally and want everything on one machine:

```bash
run_dev_server.bat
```

**Opens at:** http://localhost:8443/elfministration

### Option 3: Using Docker/Podman (Production-like)
```bash
podman build -t thebigtree-web -f Containerfile.web .
podman run -p 8443:8443 thebigtree-web
```

## What Gets Started

**Frontend Server** starts the web UI and proxies to a remote API:
- **Admin Overlay**: http://localhost:3001/elfministration
- **API Proxy**: Routes to your remote server

**Full Server** starts everything locally (requires DB):
- **Admin Overlay**: http://localhost:8443/elfministration
- **API Endpoints**: http://localhost:8443/api/*

## Configuration

### Frontend Server (Option 1 - Recommended)

Edit `dev_frontend.py` and set your API server URL:

```python
REMOTE_API_URL = "http://your-api-server.com:8443"  # ← Change this
```

Then run:
```bash
run_frontend_server.bat
```

The frontend will:
- Serve HTML/CSS/JS from your local machine
- Route all `/api/*`, `/admin/*`, `/events/*` requests to your remote server
- Allow you to edit frontend code and see changes instantly

### Full Local Stack (Option 2)

Create a `config.ini` file in the project root:

```ini
[DATABASE]
host = 127.0.0.1
port = 5432
user = bigtree
password = your_password
name = bigtree

[WEB]
listen_host = 0.0.0.0
listen_port = 8443
base_url = http://localhost:8443
jwt_secret = your-secret
```

Then run:
```bash
run_dev_server.bat
```

## Testing Your Changes

1. **Overlay Admin Panel**: Navigate to http://localhost:8443/admin/overlay
   - Test events modal, wallet management, background image picker
   - Verify venue/currency display-only fields
   - Test player list and top-up modal workflow

2. **Event Join Page**: Create an event in admin panel, then visit the join URL
   - Test "VENUE presents: TITLE" display
   - Test wallet balance display
   - Test background image rendering

3. **API Testing**: Use browser DevTools Network tab or curl:
   ```bash
   curl http://localhost:8443/admin/events
   curl http://localhost:8443/admin/venues
   ```

## Troubleshooting

### Python Not Found
If you see "Python was not found":
1. Install Python 3.8+ from https://www.python.org/downloads/
2. During installation, check "Add Python to PATH"
3. Restart your terminal/PowerShell

### Missing Dependencies
```bash
pip install -r requirements.txt
```

### Database Not Initialized
The dev server attempts to initialize the database automatically. If you see database errors, ensure your `spec.ini` has valid database configuration.

### Port Already in Use
If port 8443 is already in use, edit `spec.ini` and change `listen_port` to another port (e.g., 8080).

## VS Code Python Extension

If you have VS Code's Python extension installed:
1. Open Command Palette (Ctrl+Shift+P)
2. Type "Python: Select Interpreter"
3. Choose your Python installation
4. Then run: `python dev_server.py` in the terminal

## Live Reloading

The dev server does NOT auto-reload on file changes. After editing:
- **HTML/CSS/JS**: Just refresh your browser (Ctrl+F5 for hard refresh)
- **Python code**: Stop the server (Ctrl+C) and restart it


### Fast regression checks

Before building a container, run:

```bash
python -m compileall -q bigtree tests tools dev_frontend.py
python -m unittest discover -s tests -v
node --check bigtree/web/static/overlay/overlay.js
```

If Go dependencies are available locally, also run `go test ./...` and `go vet ./...` inside `overlay-client`. The Forest client should be built with the .NET SDK through its normal workflow.

For media performance, test with at least one large uploaded image. The media grid should request `/media/thumbs/<filename>`, explicit previews should request `/media/previews/<filename>`, and opening/copying the original should still use `/media/<filename>`.

For Verdant Conclave, create a session in Discord, confirm the game controls only work in the bound channel, then verify the web/Forest host panels can see readiness and public state without exposing living secret roles. `/conclave-create` may create a dedicated channel, use the current channel, or bind an explicitly selected existing text channel; people already able to see that channel are **not** auto-enrolled and must use Join.

For single-operator Conclave testing, open **Elfministration → Verdant Conclave → Test circle** while the session is in the lobby. **Fill to 5** creates only enough synthetic players to reach the minimum, **+1 test elf** adds another up to the normal 15-player cap, and **Clear test elves** removes them before the game starts. Synthetic players live only in the PostgreSQL game payload, use negative non-Discord IDs, and never create Discord users, BigTree principals, DMs, or private role messages. After starting, **Run test choices** submits phase-appropriate actions/votes for synthetic players only; in mixed tests they prefer synthetic targets and abstain rather than automatically condemn a real player.

The Discord public panel must label synthetic players with the test marker rather than emitting invalid user mentions, and the persistent Refresh button must use a valid Unicode emoji.


### Container/static checks

The production image is multi-stage and should be built with BuildKit/Buildx (the GitHub workflow already does this). During the image build, `tools/precompress_static.py` creates deterministic `.gz` sidecars for compressible static assets. Confirm a browser request with `Accept-Encoding: gzip` receives `Content-Encoding: gzip`, while an explicit `gzip;q=0` receives the original asset.

When testing behind Traefik, confirm `/healthz` reports the expected `build.sha`. `/readyz` should return HTTP 503 until both Discord and PostgreSQL are ready, then HTTP 200. For a Traefik address outside private/loopback ranges, configure `BIGTREE__WEB__trusted_proxy_cidrs` explicitly before validating secure cookies and forwarded client IP logging.

Cardgame regression tests cover split-hand Blackjack progression, duplicate Craps round protection, event polling and maintenance throttling. For a production smoke test, retry the same wallet-backed action nonce and confirm it is not charged or paid twice.

## Language Services regression checks

Language Services is available from **Elfministration → System → Language Services** to users with `admin:web`. The workspace exposes the effective provider/model, safe credential fingerprint/source, active TheBigTree system context, bounded memory, request diagnostics, and Discord search.

Run the language-specific contract tests with:

```bash
python -m unittest -v tests.test_language_services_contracts
```

For a manual smoke test:

1. Open Language Services and confirm the provider key is masked rather than returned to the browser.
2. Select **MiniMax**, enter an `sk-cp-…` Token Plan or `sk-api-…` PAYG key, keep `MiniMax-M3`, save, and use **Test provider**. The request diagnostics should identify MiniMax without ever returning the raw key.
3. For an `sk-cp-…` key, use **Check quota** and verify the MiniMax Token Plan response is shown only on demand; the service does not poll quota in the background.
4. Confirm the existing Discord Priest/authorised-speaker gate still blocks non-Priests before any language-provider call. Correct ritual wording must never grant an audience.
5. With reverence enforcement enabled and **Correct first; withhold the answer** selected, an authorised Priest saying only `Tree, who did X?` should receive an in-character etiquette correction rather than the requested knowledge. Addressing TheBigTree with an accepted title should allow the normal answer.
6. Confirm the emergency override helps an already-authorised communicant first rather than insisting on ceremony. It must not bypass the Priest gate.
7. Pin a global memory, refresh, and verify it survives. Delete it again.
8. Search Discord with and without a specific channel. Results should link back to Discord and are not stored as memory.
9. If answer-time Discord retrieval is desired, select one or more channels and explicitly enable **Discord retrieval for answers**. It is off by default.
10. Disable **Priest chat** and verify Priest DMs/mentions no longer invoke the language provider.

Language memory is PostgreSQL-backed and intentionally bounded for the container deployment: conversation entries are truncated to 4 KB, per-user recent history is capped, default retention is 90 days, and the default installation-wide unpinned conversation ceiling is 5,000 rows. Pinned operator notes have their own 1,000-row hard limit. Discord search is live/on-demand and does not build a local message archive. The UI exposes the actual stored text byte count and includes an explicit prune action.

## Container restart / persistent startup migration smoke test

1. Deploy the patch with the existing persistent PostgreSQL database and restart the application container.
2. On the first patched start, existing `deck_files`, `media_items`, and imported `games` should be adopted into `startup_migrations` without a full rescan where data already exists. Legacy state/contest migration may perform one final bounded pass before being marked complete.
3. Restart the application container again. Logs should show normal schema/config timing but no `running one-time startup import ...` lines for completed imports.
4. Confirm `startup_migrations` is stored in PostgreSQL; no marker file is required in the disposable application container.
5. For deliberate repair only, `BIGTREE_RECONCILE_MEDIA_ON_START=1` reruns media reconciliation, while `BIGTREE_FORCE_STARTUP_IMPORTS=1` reruns all bootstrap importers. Remove these flags after maintenance. `BIGTREE_STARTUP_IMPORT_REPORT=1` enables the legacy import report without forcing imports.

## MiniMax divine-audience smoke test
- Public `@TheBigTree` counts as the canonical divine address.
- Existing Priest authorization is never re-requested by the model.
- Empty adaptive M3 completions retry once with thinking disabled.
- Normal TheBigTree conversation reserves at least 1,200 provider output tokens even when an older database still contains the former 400-token setting. This is a ceiling, not a target response length.
- If the provider reports a token-limit/length finish reason, the first completion must be discarded and retried once with a larger direct budget; diagnostics should show the finish reason, effective budget and completion retry. A second truncated completion must surface as an error rather than being posted to Discord.
- A `correct_only` reverence response should use direct reasoning, stay within one or two short sentences (at most 90 words), and must not spend its response budget on atmospheric scene-setting before the etiquette correction.


## Identity & Access foundation

- Run `python -m unittest tests.test_access_control_contracts -v`.
- Verify an existing Priest/ess can still address TheBigTree but cannot use `/commune` unless they separately have operator/Elfministrator authority.
- Verify an existing BigTree operator can use `/commune` without becoming a Priest.
- Verify legacy web tokens with `admin:*` satisfy routes requiring `admin:web`; existing exact legacy scopes continue to work.
- With an admin token, inspect `GET /admin/access/catalog` and use `POST /admin/access/evaluate` with a Discord user ID and capability to see an explainable allow/deny decision.
- Confirm PostgreSQL contains the `access_*` tables and that no IAM state files are created inside the application container.
