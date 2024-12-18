import bigtree
import re

def find_url(message):
    urls = re.search("(?P<url>https?://[^\s]+)", message).group("url")
    return urls