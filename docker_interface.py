'''boilerplate interactions with docker i need'''

from pathlib import Path
from typing import Tuple
import argparse
import logging


import docker

from util import QMK_DOCKER_IMAGE, QMK_FIRMWARE_DIR, VIAL_GIT_URL, DEFAULT_BRANCH

log = logging.getLogger(__name__)


def exec_run_wrapper(container: docker.models.containers.Container,
                     cmd: str) -> Tuple[int, str]:
    '''Wraps output decoded'''
    log.debug("docker exec %s %s", container.name, cmd)
    exit_code, bytestring_output = container.exec_run(cmd)
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
    except docker.errors.APIError:
        pass


def prepare_container(args: argparse.Namespace) -> docker.models.containers.Container:
    '''create docker volume, spin up container, mount everything in right location'''
    if args.verbose:
        log.setLevel(logging.DEBUG)
    client = docker.from_env()
    # create volume for qmk if necessary
    try:
        client.volumes.get('qmk')
    except docker.errors.NotFound:
        client.volumes.create('qmk')
    fw_dir_mnt = docker.types.Mount('/vial', str(Path.cwd() / 'vial'), type="bind")
    vial_container = client.containers.run(QMK_DOCKER_IMAGE,
                                           name='vial',
                                           detach=True,
                                           tty=True,
                                           volumes=['qmk:/qmk_firmware'],
                                           mounts=[fw_dir_mnt],
                                           working_dir=QMK_FIRMWARE_DIR,
                                           auto_remove=True)
    exit_code, _ = exec_run_wrapper(vial_container, f'git -C {QMK_FIRMWARE_DIR} status')
    if not exit_code:
        # just pull if its already there
        exec_run_wrapper(vial_container,
                         f'git -C {QMK_FIRMWARE_DIR} pull origin {DEFAULT_BRANCH} --ff-only')
    else:
        # clone if it is not downloaded laready
        exec_run_wrapper(vial_container,
                         f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
    exec_run_wrapper(vial_container,
                     f'python3 -m pip install -r {QMK_FIRMWARE_DIR}/requirements.txt')
    exec_run_wrapper(vial_container, 'make git-submodule')
    return vial_container
