#!/usr/bin/env python3
"""
Frontend-only development server that serves static files and UI, with API proxy.
Connects to a remote BigTree API server.
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from aiohttp import web

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("frontend_dev")

# Configuration
WEB_HOST = "0.0.0.0"
WEB_PORT = 3001
# Read API URL from environment variable; no hardcoded IP in code
REMOTE_API_URL = os.getenv("BIGTREE_API_URL", "http://localhost:8443")
if REMOTE_API_URL == "http://localhost:8443":
    logger.warning("⚠️  BIGTREE_API_URL not set. Using default: http://localhost:8443")
    logger.warning("    Set the environment variable to your actual API server, e.g.:")
    logger.warning("    $env:BIGTREE_API_URL = 'http://192.168.0.132:8443'")
    logger.warning("    or: export BIGTREE_API_URL='http://192.168.0.132:8443'")

async def serve_html(request):
    """Serve the overlay HTML with injected API URL and background image."""
    html_file = Path(__file__).parent / "bigtree" / "web" / "templates" / "overlay.html"
    if not html_file.exists():
        return web.Response(text="overlay.html not found", status=404)
    
    html_content = html_file.read_text(encoding='utf-8')
    
    # Replace template variable for admin background (serve locally from static)
    admin_background = "/static/images/admin_background.png"
    html_content = html_content.replace("{ADMIN_BACKGROUND}", admin_background)
    
    # Inject API base URL pointing to LOCAL PROXY (not remote server)
    # All requests will be proxied from localhost:3001 to the remote server
    injection = f"""
    <script>
    window.API_BASE_URL = "http://localhost:3001";
    console.log("[BigTree Dev] Using LOCAL PROXY at", window.API_BASE_URL);
    console.log("[BigTree Dev] Remote API:", "{REMOTE_API_URL}");
    console.log("[BigTree Dev] Check Storage tab - localStorage.getItem('bt_api_key') should have your key");
    </script>
    """
    html_content = html_content.replace("</head>", f"{injection}</head>", 1)
    
    # Add CORS headers for images loaded from remote server
    return web.Response(text=html_content, content_type="text/html", headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key"
    })

async def proxy_api(request):
    """Proxy API requests to the remote server."""
    import aiohttp
    
    path = request.match_info.get('path', '')
    method = request.method
    
    # Reconstruct the full path by detecting which prefix was matched
    # The route patterns are /{prefix}/{path:.*}, so we need to extract prefix from request.path
    full_path = path  # Default: use path as-is
    
    # Determine which prefix to use based on the original request path
    prefixes = ['api', 'admin', 'events', 'bingo', 'discord', 'contests', 'auth']
    for prefix in prefixes:
        if request.path.startswith(f'/{prefix}/'):
            full_path = f"{prefix}/{path}"
            break
    
    # Build target URL
    target_url = f"{REMOTE_API_URL}/{full_path}"
    if request.query_string:
        target_url += f"?{request.query_string}"
    
    logger.info(f"📡 {method} {request.path} -> {target_url}")
    
    # Copy headers, don't strip Authorization
    headers = dict(request.headers)
    headers.pop('Host', None)
    
    # Log auth headers for debugging (masked)
    has_auth = False
    if 'Authorization' in headers:
        logger.info(f"   ✓ Authorization: {headers['Authorization'][:20]}...")
        has_auth = True
    if 'X-API-Key' in headers:
        logger.info(f"   ✓ X-API-Key: {headers['X-API-Key'][:20]}...")
        has_auth = True
    if not has_auth:
        logger.warning(f"   ⚠️  NO AUTH HEADERS FOUND")
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(force_close=True)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Prepare request body for POST/PUT
            data = None
            if method in ['POST', 'PUT']:
                data = await request.read()
            
            async with session.request(method, target_url, headers=headers, data=data, allow_redirects=False) as resp:
                response_text = await resp.text()
                response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ['content-encoding', 'content-type']}
                # Add CORS headers
                response_headers['Access-Control-Allow-Origin'] = '*'
                response_headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response_headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
                
                # Log response
                if resp.status >= 400:
                    logger.warning(f"   ❌ {resp.status}: {response_text[:200]}")
                else:
                    logger.info(f"   ✓ {resp.status}")
                
                return web.Response(
                    text=response_text,
                    status=resp.status,
                    content_type=resp.content_type,
                    headers=response_headers
                )
    except Exception as e:
        logger.error(f"   💥 Proxy error: {e}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return web.json_response({"error": str(e)}, status=502)

async def serve_static(request):
    """Serve static files (CSS, JS, images)."""
    file_path = request.match_info.get('path', '')
    static_dir = Path(__file__).parent / "bigtree" / "web" / "static"
    full_path = (static_dir / file_path).resolve()
    
    # Security: prevent directory traversal
    try:
        full_path.relative_to(static_dir)
    except ValueError:
        return web.Response(text="Forbidden", status=403)
    
    if full_path.is_file():
        return web.FileResponse(full_path)
    
    return web.Response(text="Not found", status=404)

async def proxy_image(request):
    """Proxy image requests to the remote server."""
    import aiohttp
    
    # Get the full path that was requested
    path = request.match_info.get('path', '')
    
    # Build target URL
    target_url = f"{REMOTE_API_URL}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string}"
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(force_close=True)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(target_url, allow_redirects=False) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    response_headers = {
                        'Access-Control-Allow-Origin': '*',
                        'Cache-Control': 'public, max-age=3600'
                    }
                    return web.Response(
                        body=data,
                        status=resp.status,
                        content_type=resp.content_type,
                        headers=response_headers
                    )
                else:
                    return web.Response(status=resp.status, text="Image not found")
    except Exception as e:
        logger.error(f"Image proxy error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return web.Response(status=502, text="Image proxy error")

async def cors_options_handler(request):
    """Handle CORS preflight requests."""
    return web.Response(
        status=200,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key',
            'Access-Control-Max-Age': '3600'
        }
    )

async def main():
    logger.info(f"🌲 Starting BigTree Frontend Dev Server")
    logger.info(f"📝 UI Server: http://localhost:{WEB_PORT}")
    logger.info(f"🔌 API Server: {REMOTE_API_URL}")
    logger.info("")
    logger.info("To change the API server, edit REMOTE_API_URL in dev_frontend.py")
    logger.info("")
    
    app = web.Application()
    
    # Routes
    app.router.add_get('/', serve_html)
    app.router.add_get('/elfministration', serve_html)
    app.router.add_static('/static', Path(__file__).parent / "bigtree" / "web" / "static")
    
    # API proxy routes with CORS
    app.router.add_route('*', '/api/{path:.*}', proxy_api)
    app.router.add_route('*', '/admin/{path:.*}', proxy_api)
    app.router.add_route('*', '/events/{path:.*}', proxy_api)
    app.router.add_route('*', '/bingo/{path:.*}', proxy_api)
    app.router.add_route('*', '/discord/{path:.*}', proxy_api)
    app.router.add_route('*', '/contests/{path:.*}', proxy_api)
    app.router.add_route('*', '/auth/{path:.*}', proxy_api)
    app.router.add_route('*', '/media/{path:.*}', proxy_image)
    app.router.add_route('*', '/uploads/{path:.*}', proxy_image)
    
    # CORS preflight
    app.router.add_options('/{path:.*}', cors_options_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    
    logger.info(f"✅ Server ready!")
    logger.info(f"📂 Open: http://localhost:{WEB_PORT}/elfministration")
    logger.info("")
    logger.info("Press Ctrl+C to stop")
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping server...")
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
