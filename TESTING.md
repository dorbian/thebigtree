# Testing BigTree Frontend Locally

## Quick Start (With Remote API)

### Option 1: Frontend Server (Recommended for Frontend Testing)
This serves only the UI and proxies API calls to a remote server.

```bash
# Edit dev_frontend.py and change REMOTE_API_URL to your API server
# Then run:
run_frontend_server.bat
```

**Opens at:** http://localhost:3000/elfministration

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
- **Admin Overlay**: http://localhost:3000/elfministration
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
