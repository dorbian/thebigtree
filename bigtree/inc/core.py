"""
Core utilities for BigTree backend.
Provides helper functions for URL parsing and view management.
"""

import bigtree
import re
import glob
import os
import pathlib


def find_url(message: str) -> str | bool:
    """
    Extract the first HTTP(S) URL from a message.
    
    Args:
        message: The text to search for URLs
    
    Returns:
        The first URL found, or False if no URL present
    """
    try:
        urls = re.search("(?P<url>https?://[^\s]+)", message).group("url")
    except AttributeError:
        return False
    return urls


def get_views() -> list[str]:
    """
    List all available view templates.
    
    Returns:
        List of view names (without .py extension) from bigtree/views directory
    """
    try:
        view_dir = os.path.join(os.getcwd(), 'bigtree/views')
        if os.path.exists(view_dir):
            files = os.listdir(view_dir)
            return [f.split('.')[0] for f in files if f.endswith('.py')]
    except Exception as e:
        import logging
        logging.warning("Failed to load views: %s", e)
    return []
