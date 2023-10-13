'''utility function and variables'''

from pathlib import Path
from typing import Tuple
import logging

import requests


REPO_OWNER = 'vial-kb'
REPO_NAME = 'vial-qmk'
DEFAULT_BRANCH = 'vial'

VIAL_GIT_URL = f'https://github.com/{REPO_OWNER}/{REPO_NAME}'
VIAL_LATEST_COMMIT_URL = \
    f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/' \
    f'{DEFAULT_BRANCH}'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/qmk_cli'
PAGE_HEADER = 'vial-qmk nightly'
COMMIT_ID_FILE = '.commit_id'
PAGE_CHAR_WIDTH = 72

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def freshness_check(cwd: Path) -> Tuple[str, bool]:
    '''
    Write a little file with the commit ID of HEAD for git repo,
    and return True if it matches repo on pulling from git most recently,
    and save us work of recompiling files all the way over again
    '''
    latest_commit = requests.get(VIAL_LATEST_COMMIT_URL, timeout=30)
    latest_commit_dict = latest_commit.json()
    new_commit_id = latest_commit_dict['sha']

    old_commit_id_file = Path(cwd, COMMIT_ID_FILE)
    if old_commit_id_file.exists():
        old_commit_id = old_commit_id_file.read_text(encoding='utf-8')
        log.debug("Old build commit hash: %s, new build commit hash: %s",
                  old_commit_id, new_commit_id)
        if old_commit_id == new_commit_id:
            return old_commit_id, True
    return new_commit_id, False


def set_last_successful_build(cwd: Path, new_commit_id: str) -> None:
    """Save file with latest successful commit id"""
    old_commit_id_file = Path(cwd, COMMIT_ID_FILE)
    old_commit_id_file.write_text(new_commit_id, encoding='utf-8')
