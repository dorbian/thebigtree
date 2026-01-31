"""
Contest management utilities for BigTree.
Handles contest creation, updates, and data persistence.
"""

import bigtree
from tinydb import TinyDB, Query
import os
from typing import Any, Dict, Optional
from bigtree.inc.logging import logger


def contest_management(contest_id: int, insertdata: Dict[str, Any], command: str) -> Any:
    """
    Manage contest data (create, update, add entries).
    
    Args:
        contest_id: The contest ID
        insertdata: Data to insert or update
        command: Operation to perform ("update" or "add")
    
    Returns:
        Return value from TinyDB operation, or empty string for update
    """
    logger.debug("[contest] managing contest_id=%s command=%s", contest_id, command)
    filepath = os.path.join(bigtree.contest_dir, f'{contest_id}.json')
    logger.debug("[contest] database path=%s", filepath)

    if os.path.exists(filepath):
        contest_list = insertdata
    else:
        contest_list = {
            'name': 'tree',
            'file': 'tree',
            'filename': 'fakename.png',
            'votes': ['test']
        }
        # add the new contest in the contestlist
        bigtree.contestid.append(contest_id)
        logger.info("[contest] created new contest_id=%s", contest_id)

    contestdb = TinyDB(filepath)

    if command == "update":
        logger.debug("[contest] updating contest_id=%s data=%s", contest_id, contest_list)
        returnval = ""
    elif command == "add":
        returnval = contestdb.insert(contest_list)
        logger.info("[contest] added entry to contest_id=%s", contest_id)
    else:
        logger.warning("[contest] unknown command=%s", command)
        returnval = None

    return returnval


