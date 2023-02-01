'''boilerplate interactions with docker i need'''

import argparse
import logging
import subprocess
import sys

from util import QMK_DOCKER_IMAGE, QMK_FIRMWARE_DIR, VIAL_GIT_URL

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def docker_run_cmd(args: argparse.Namespace, container_id: str, cmd: str, line: str = None,
                   check: bool = True, get_stdout: bool = False) -> subprocess.CompletedProcess:
    '''Frontend to simplify running cmd in docker'''
    subprocess_cmd = f'docker {cmd} {container_id} {line}'
    log_subprocess_cmd = f'docker {cmd} {container_id[0:6]} {line}'
    log.debug('Running: %s', log_subprocess_cmd)
    stdout_pipe = subprocess.PIPE if get_stdout else subprocess.DEVNULL
    stderr_pipe = subprocess.STDOUT if get_stdout else subprocess.DEVNULL
    try:
        proc = subprocess.run(subprocess_cmd, shell=True, stdout=stdout_pipe,
                              stderr=stderr_pipe, check=check)
        return proc
    except subprocess.CalledProcessError:
        log.exception("Exception raised by failure to run command in docker")
        if not args.debug:
            close_containers(container_id)
        sys.exit(1)


def docker_cmd_stdout(args: argparse.Namespace, container_id: str, line: str,
                      check: bool = True) -> str:
    '''Frontend to simplify getting stdout from docker command'''
    proc = docker_run_cmd(args, container_id, 'exec', line, check, True)
    return proc.stdout.decode('utf-8')


def close_containers(container_id: str) -> None:
    '''Close qmkfm/basecontainer docker containers when needed'''
    log.debug("Closing docker containers...")
    subprocess.run(f'docker stop {container_id}', shell=True, check=True)
    subprocess.run(f'docker container rm {container_id}', shell=True, check=True)


def prepare_container(args: argparse.Namespace) -> str:
    '''Spin up docker container from qmkfm/base_container and return container ID'''
    if args.debug:
        container_id = 'vial'
    else:
        log.debug("Creating docker containers")
        try:
            create_container_command = \
                f'docker run -dit --name vial --workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
            container_id = subprocess.check_output(create_container_command,
                                                   shell=True, encoding='utf8').strip()
        except subprocess.CalledProcessError:
            sys.exit(125)

    if not args.debug:
        docker_run_cmd(args, container_id, 'exec', 'python3 -m pip install qmk')
        docker_run_cmd(args, container_id, 'exec',
                       f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')

    return container_id
