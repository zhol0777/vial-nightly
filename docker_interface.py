'''boilerplate interactions with docker i need'''

import argparse
import logging
import sys
from pathlib import Path
from typing import Tuple

import docker
from docker.errors import APIError
from docker.models.containers import Container
from docker.types import Mount

from util import DEFAULT_BRANCH, QMK_FIRMWARE_DIR

log = logging.getLogger(__name__)


def exec_run_wrapper(container: Container,
                     cmd: str,
                     workdir: str = '/qmk_firmware',
                     debug_log_output: bool = True,
                     exit_on_nonzero: bool = False) -> Tuple[int, str]:
    '''Wraps output decoded'''
    log.debug("docker exec %s %s", container.name, cmd)
    exit_code, bytestring_output = container.exec_run(cmd, workdir=workdir)  # type: ignore
    if debug_log_output:
        log.debug("exit_code: %s, output: %s", exit_code, bytestring_output.decode('utf-8'))
    if exit_code:
        log.error("Command failed: %s", cmd)
        if exit_on_nonzero:
            close_containers('vial')
            sys.exit(0)
    return exit_code, bytestring_output.decode('utf-8')


def exec_run_wrapper_no_bail(container: Container,
                             cmd: str,
                             workdir: str = '/qmk_firmware') -> Tuple[int, str]:
    '''Wraps output decoded, does not bail on nonzero exit'''
    log.debug("docker exec %s %s", container.name, cmd)
    exit_code, bytestring_output = container.exec_run(cmd, workdir=workdir)  # type: ignore
    log.debug("exit_code: %s, output: %s", exit_code, bytestring_output.decode('utf-8'))
    return exit_code, bytestring_output.decode('utf-8')


def close_containers(container_id: str) -> None:
    '''Close qmkfm/basecontainer docker containers when needed'''
    log.debug("Closing docker containers...")
    client = docker.from_env()
    container = client.containers.get(container_id)
    container.stop()
    try:
        container.remove()
    except APIError:
        pass


def prepare_container(args: argparse.Namespace) -> Container:
    '''create docker volume, spin up container, mount everything in right location'''
    if args.verbose:
        log.setLevel(logging.DEBUG)
    client = docker.from_env()
    if not client.images.list(name='vial-nightly'):
        client.images.build(path='.', tag='vial-nightly')
    vial_local_path = Path.cwd() / 'vial'
    if not vial_local_path.exists():
        vial_local_path.mkdir()
    fw_dir_mnt = Mount('/vial', str(vial_local_path), type="bind")
    vial_container = client.containers.run('vial-nightly',
                                           name='vial',
                                           detach=True,
                                           tty=True,
                                           # reusing volume seems to cause uf2 complation issue
                                           # volumes=['qmk:/qmk_firmware'],
                                           mounts=[fw_dir_mnt],
                                           working_dir=QMK_FIRMWARE_DIR,
                                           auto_remove=True)
    exec_run_wrapper(vial_container,
                     f'git -C {QMK_FIRMWARE_DIR} pull origin {DEFAULT_BRANCH} --ff-only')
    exec_run_wrapper(vial_container,
                    f'python3 -m pip install -U -r {QMK_FIRMWARE_DIR}/requirements.txt',
                     exit_on_nonzero=True)
    exec_run_wrapper(vial_container, 'make git-submodule',
                     exit_on_nonzero=True)
    return vial_container
