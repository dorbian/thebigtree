import bigtree
from tinydb import TinyDB, Query
import os

def contest_management(contest_id, insertdata, command):
    global contestid 
    filepath = bigtree.contest_dir / f'{contest_id}.json'

    if os.path.exists(filepath):
        contest_list = insertdata

    if not os.path.exists(filepath):
        contest_list = {
            'name': 'tree',
            'file': 'tree',
            'filename': 'fakename.png',
            'votes': ['test']
            }
        # add the new contest in the contestlist
        bigtree.contestid.append(contest_id)

    contestdb = TinyDB(filepath)

    if command == "update":
        print(contest_list)
        returnval = ""

    if command == "add":
        returnval = contestdb.insert(contest_list)

    return returnval