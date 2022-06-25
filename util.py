'''utility function and variables'''

from pathlib import Path

VIAL_GIT_URL = 'https://github.com/vial-kb/vial-qmk'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/base_container'
PAGE_HEADER = 'vial-qmk nightly'
FIRMWARE_TAR = 'vial-files.tar'
COMMIT_ID_FILE = '.commit_id'
PAGE_CHAR_WIDTH = 72

def files_still_fresh(git_commit_id: str, cwd: Path) -> bool:
    '''
    Write a little file with the commit ID of HEAD for git repo,
    and return True if it matches repo on pulling from git most recently,
    and save us work of recompiling files all the way over again
    '''
    old_commit_id_file = Path(cwd, COMMIT_ID_FILE)
    if old_commit_id_file.exists():
        old_commit_id = old_commit_id_file.read_text(encoding='utf-8')
        if old_commit_id == git_commit_id:
            return True
    old_commit_id_file.write_text(git_commit_id, encoding='utf-8')
    return False
