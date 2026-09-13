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

For Verdant Conclave, create a session in Discord, confirm the game controls only work in the bound channel, then verify the web/Forest host panels can see readiness and public state without exposing living secret roles.


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
2. Use **Test provider** and verify the request status/token counters update (this performs one billable provider request).
3. Pin a global memory, refresh, and verify it survives. Delete it again.
4. Search Discord with and without a specific channel. Results should link back to Discord and are not stored as memory.
5. If answer-time Discord retrieval is desired, select one or more channels and explicitly enable **Discord retrieval for answers**. It is off by default.
6. Disable **Priest chat** and verify Priest DMs/mentions no longer invoke the language provider.

Conversation memory stores only a bounded set of successful Priest exchanges per user. Pinned notes are retained until an operator deletes them; clearing conversation history leaves pinned notes intact.
