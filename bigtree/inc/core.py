import bigtree
import re

def find_url(message):
    try:
        urls = re.search("(?P<url>https?://[^\s]+)", message).group("url")
    except AttributeError:
        urls = False
    else:
        return urls