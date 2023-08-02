'''boilerplate interactions with docker i need'''

from pathlib import Path
import argparse
import logging
import os
import subprocess
import sys

from util import QMK_DOCKER_IMAGE, QMK_FIRMWARE_DIR, VIAL_GIT_URL, DEFAULT_BRANCH

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def docker_run_cmd(args: argparse.Namespace, container_id: str, cmd: str, line: str = '',
                   check: bool = True, get_stdout: bool = False) -> subprocess.CompletedProcess:
    '''Frontend to simplify running cmd in docker'''
    if args.verbose:
        log.setLevel(logging.DEBUG)
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
    '''Spin up docker container from qmkfm/qmk_cli and return container ID'''
    if args.verbose:
        log.setLevel(logging.DEBUG)

    if args.debug:
        container_id = 'vial'
    else:
        # prepare serving for creation/refresh
        Path('qmk_firmware').mkdir(exist_ok=True)
        Path('vial').mkdir(exist_ok=True)
        log.debug("Creating docker containers")
        try:
            create_container_command = \
                f'docker run -dit --name vial --cpus="3" '\
                f'--mount type=bind,source={Path.cwd()}/qmk_firmware,target={QMK_FIRMWARE_DIR} '\
                f'--mount type=bind,source={Path.cwd()}/vial,target=/vial '\
                f'--workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
            container_id = subprocess.check_output(create_container_command,
                                                   shell=True, encoding='utf8').strip()
        except subprocess.CalledProcessError:
            sys.exit(125)

    if not args.debug:
        # see if git directory exists properly
        error_code = subprocess.call(['git', '-C', 'qmk_firmware', 'status'],
                                     stderr=subprocess.STDOUT, stdout=open(os.devnull, 'w'))
        if not error_code:
            # just pull if it's already there
            log.debug("pulling git from origin due to exit code %s", error_code)
            docker_run_cmd(args, container_id, 'exec',
                           f'git -C {QMK_FIRMWARE_DIR} pull origin {DEFAULT_BRANCH}')
        else:
            # clone if it isn't downloaded yet
            log.debug("folder not there, cloning shallow")
            docker_run_cmd(args, container_id, 'exec',
                           f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
        docker_run_cmd(args, container_id, 'exec',
                       f'python3 -m pip install -r {QMK_FIRMWARE_DIR}/requirements.txt')
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')

    return container_id
