import bigtree
import re
import glob
import os
import pathlib

def find_url(message):
    try:
        urls = re.search("(?P<url>https?://[^\s]+)", message).group("url")
    except AttributeError:
        urls = False
    else:
        return urls

def get_views():
    l=os.listdir(os.path.join(os.getcwd(),'bigtree/views'))
    li=[x.split('.')[0] for x in l]
    return li