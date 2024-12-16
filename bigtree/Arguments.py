"""
Command line arguments for when starting the bot.
"""

import bigtree
import os

def optsargs():
    from optparse import OptionParser
    p = OptionParser()
    p.add_option('-t', '--token', dest='token',default='' help='HelpText' )
    bigtree.options, bigtree.args = p.parse_args()