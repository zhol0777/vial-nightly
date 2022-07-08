'''utility function and variables'''

from pathlib import Path
from typing import Tuple

import requests


REPO_OWNER = 'vial-kb'
REPO_NAME = 'vial-qmk'
DEFAULT_BRANCH = 'vial'

VIAL_GIT_URL = f'https://github.com/{REPO_OWNER}/{REPO_NAME}'
VIAL_LATEST_COMMIT_URL = \
    f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{DEFAULT_BRANCH}'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/base_container'
PAGE_HEADER = 'vial-qmk nightly'
FIRMWARE_TAR = 'vial-files.tar'
COMMIT_ID_FILE = '.commit_id'
PAGE_CHAR_WIDTH = 72


def freshness_check(cwd: Path) -> Tuple[str, bool]:
    '''
    Write a little file with the commit ID of HEAD for git repo,
    and return True if it matches repo on pulling from git most recently,
    and save us work of recompiling files all the way over again
    '''
    latest_commit = requests.get(VIAL_LATEST_COMMIT_URL)
    latest_commit_dict = latest_commit.json()
    new_commit_id = latest_commit_dict['sha']

    old_commit_id_file = Path(cwd, COMMIT_ID_FILE)
    if old_commit_id_file.exists():
        old_commit_id = old_commit_id_file.read_text(encoding='utf-8')
        if old_commit_id == new_commit_id:
            return new_commit_id, True
    old_commit_id_file.write_text(new_commit_id, encoding='utf-8')
    return new_commit_id, False
