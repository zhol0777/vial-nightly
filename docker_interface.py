'''boilerplate interactions with docker i need'''

import argparse
import logging
import subprocess
import sys

from pathlib import Path
from typing import Tuple

from util import files_still_fresh
from util import QMK_DOCKER_IMAGE, QMK_FIRMWARE_DIR, VIAL_GIT_URL

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def docker_run_cmd(args: argparse.Namespace, container_id: str, cmd: str, line: str = None,
                   check: bool=True, get_stdout: bool=False) -> subprocess.CompletedProcess:
    '''Frontend to simplify running cmd in docker'''
    subprocess_cmd = f'docker {cmd} {container_id} {line}'
    log_subprocess_cmd = f'docker {cmd} {container_id[0:6]} {line}'
    log.info('Running: %s', log_subprocess_cmd)
    stdout_pipe = subprocess.PIPE if get_stdout else subprocess.DEVNULL
    try:
        proc = subprocess.run(subprocess_cmd, shell=True, stdout=stdout_pipe,
                              stderr=subprocess.DEVNULL, check=check)
        return proc
    except subprocess.CalledProcessError:
        log.exception("Exception raised by failure to run command in docker")
        if not args.debug:
            close_containers(container_id)
        sys.exit(1)


def docker_cmd_stdout(args: argparse.Namespace, container_id: str, line: str,
                      check: bool=True) -> str:
    '''Frontend to simplify getting stdout from docker command'''
    proc = docker_run_cmd(args, container_id, 'exec', line, check, True)
    return proc.stdout.decode('utf-8')


def close_containers(container_id: str) -> None:
    '''Close qmkfm/basecontainer docker containers when needed'''
    log.info("Closing docker containers...")
    subprocess.run(f'docker stop {container_id}', shell=True, check=True)
    subprocess.run(f'docker container rm {container_id}', shell=True, check=True)


def prepare_container(args: argparse.Namespace, cwd: Path) -> Tuple[str, str]:
    '''Spin up docker container from qmkfm/base_container and return container ID'''
    if args.debug:
        container_id = 'vial'
    else:
        log.info("Creating docker containers")
        try:
            create_container_command = \
                f'docker run -dit --name vial --workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
            container_id = subprocess.check_output(create_container_command,
                                                   shell=True, encoding='utf8').strip()
        except subprocess.CalledProcessError:
            sys.exit(125)

    if not args.debug:
        docker_run_cmd(args, container_id, 'exec',
                       f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
        git_commit_id = docker_cmd_stdout(args, container_id, 'git rev-parse HEAD').strip()
        if files_still_fresh(git_commit_id, cwd) and not args.force:
            log.info("Files are still fresh! Skipping compilation!")
            close_containers(container_id)
            sys.exit(0)
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')

    return container_id, git_commit_id
