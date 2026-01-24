#!/usr/bin/env python3
"""
Development server for testing BigTree web frontend locally.
Runs the web server without the Discord bot.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add bigtree to path
sys.path.insert(0, str(Path(__file__).parent))

import bigtree
from bigtree.inc import webserver

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("dev_server")

async def main():
    logger.info("🌲 Starting BigTree development web server...")
    
    # Initialize minimal BigTree components (without Discord bot)
    try:
        # Initialize settings
        if hasattr(bigtree, 'load_settings'):
            bigtree.load_settings()
            logger.info("✓ Settings loaded")
        
        # Initialize database if needed
        if hasattr(bigtree, 'init_database'):
            bigtree.init_database()
            logger.info("✓ Database initialized")
        
    except Exception as e:
        logger.warning(f"⚠ Some initialization failed (continuing anyway): {e}")
    
    # Start web server
    try:
        server = await webserver.ensure_webserver()
        cfg = server._cfg
        host = cfg.get('host', '0.0.0.0')
        port = cfg.get('port', 8443)
        
        logger.info(f"🚀 Web server running at http://{host}:{port}")
        logger.info(f"📂 Overlay admin: http://localhost:{port}/admin/overlay")
        logger.info(f"📂 Event join: http://localhost:{port}/events/<code>")
        logger.info("\nPress Ctrl+C to stop the server")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping server...")
    except Exception as e:
        logger.error(f"💥 Server error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
