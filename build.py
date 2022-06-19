#!/usr/bin/python3

'''
Mostly just builds vial firmware blobs and does some organizing and touching up index.html
'''

import argparse
import glob
import logging
import subprocess
import shutil
import sys

from pathlib import Path, PurePath
from threading import Thread

from ansi2html import Ansi2HTMLConverter
from jinja2 import Template

VIAL_GIT_URL = 'https://github.com/vial-kb/vial-qmk'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/base_container'
PAGE_HEADER = 'vial-qmk nightly'
FIRMWARE_TAR = 'vial-files.tar'
COMMIT_ID_FILE = '.commit_id'
PAGE_CHAR_WIDTH = 72

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def parse_args():
    '''Parse two arguments, one for debug mode, other to just remember to close containers'''
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true')
    parser.add_argument('-close-docker-containers', '-cdc', action='store_true')
    parser.set_defaults(debug=False, close_docker_containers=False)
    args = parser.parse_args()
    return args


def docker_run_cmd(args: argparse.Namespace, container_id: str, cmd: str, line: str = None):
    '''Frontend to simplify running cmd in docker'''
    try:
        subprocess_cmd = f'docker {cmd} {container_id} {line}'
        log.info('Running: %s', subprocess_cmd)
        subprocess.run(subprocess_cmd, shell=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        log.exception("Exception raised by failure to run command in docker")
        if not args.debug:
            close_containers(container_id)
        sys.exit(1)


def docker_cmd_stdout(container_id: str, line: str):
    '''Frontend to simplify getting stdout from docker command'''
    subprocess_cmd = f'docker exec {container_id} {line}'
    log.info('Running: %s', subprocess_cmd)
    proc = subprocess.run(f'docker exec {container_id} {line}', shell=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding='utf8', check=False)
    return proc.stdout


def close_containers(container_id: str):
    '''Close qmkfm/basecontainer docker containers when needed'''
    log.info("Closing docker containers...")
    subprocess.run(f'docker stop {container_id}', shell=True, check=True)
    subprocess.run(f'docker container rm {container_id}', shell=True, check=True)


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


def main():
    '''
    Spin up docker container for qmkfm/base_container
    Pull vial-qmk and init sub-modules
    Build all possible firmware with vial keymap, grabbing output along the way
    Clean and organize firmware into other folder in container
    Copy files over to host
    Parse through build output and document why each build fails
    Save build failures and general build successes to respective html pages
    Then pretty it up
    '''
    args = parse_args()

    if args.close_docker_containers:
        close_containers('vial')
        sys.exit(0)

    cwd = Path.cwd()
    vial_dir = Path(cwd, 'vial')

    container_id, git_commit_id = prepare_container(args, cwd)

    total_build_output = compile_within_container(args, container_id)

    log.info("Copying tarball to local")
    subprocess.run(f'docker cp {container_id}:/vial -> {FIRMWARE_TAR}', shell=True,
                   stdout=subprocess.DEVNULL, check=True)

    # prepare serving for creation/refresh
    Path('vial').mkdir(exist_ok=True)

    # this has no subdirectories, so no need to recurse
    for dir_file in vial_dir.iterdir():
        dir_file.unlink()
    template_path = Path(cwd, 'templates', 'template.html.jinja')
    html_template = Template(template_path.read_text(encoding='utf8'),
                             trim_blocks=True, lstrip_blocks=True)

    log.info("Untar tarball")
    subprocess.run(f'tar -xvf {FIRMWARE_TAR}', shell=True, stdout=subprocess.DEVNULL, check=True)
    Path(cwd, FIRMWARE_TAR).unlink()

    fw_files = []
    for fw_file in vial_dir.iterdir():
        fw_files.append(fw_file.name)
    fw_files.sort()

    git_log = docker_cmd_stdout(container_id, 'git log --decorate')
    git_log = git_log.replace('<', '(')
    git_log = git_log.replace('>', ')')
    template_data = {
        'page_header': PAGE_HEADER,
        'git_commit_id': git_commit_id,
        'build_time': subprocess.check_output("date", shell=True, encoding='utf8'),
        'git_log': git_log,
        'builds': [],
        'fw_files': fw_files
    }

    open_threads: list[Thread] = []
    for line in total_build_output.split('\n'):
        new_thread = Thread(target=process_build_output,
                            args=(line, vial_dir, container_id, template_data))
        open_threads.append(new_thread)
        new_thread.start()

    for open_thread in open_threads:
        open_thread.join()

    template_data['builds'] = sorted(template_data['builds'], key=lambda d: d['sort_line'])

    index_html_path = Path(vial_dir, 'index.html')
    with open(index_html_path, 'w', encoding='utf8') as index_html:
        index_html.write(html_template.render(template_data))

    shutil.copyfile(Path(cwd, 'favicon.ico'),
                    Path(vial_dir, 'favicon.ico'))

    if not args.debug:
        close_containers(container_id)


def prepare_container(args: argparse.Namespace, cwd: Path) -> (str, str):
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
        git_commit_id = docker_cmd_stdout(container_id, 'git rev-parse HEAD').strip()
        if files_still_fresh(git_commit_id, cwd):
            log.info("Files are still fresh! Skipping compilation!")
            close_containers(container_id)
            sys.exit(0)
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')

    return container_id, git_commit_id


def compile_within_container(args: argparse.Namespace, container_id: str) -> str:
    '''Run commands to compile all vial fw within container provided'''
    # thank you piginzoo for showing me what i did wrong here
    total_build_output = docker_cmd_stdout(container_id, 'qmk multibuild -j`nproc` -km vial')

    docker_run_cmd(args, container_id, 'exec', 'qmk clean')
    docker_run_cmd(args, container_id, 'exec', 'mkdir -p /vial')
    docker_run_cmd(args, container_id, 'exec',
                   "find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +")

    return total_build_output


def process_build_output(line: str, vial_dir: str, container_id: str, template_data: dict):
    '''Build the list of build lines and thread each build'''
    conv = Ansi2HTMLConverter(dark_bg=True)
    # line example:
    # Build arisu:vial                                                        [WARNINGS]
    build_string = ' '.join(line.split()[0:2])
    build_spacing = ' ' * (PAGE_CHAR_WIDTH - len(build_string))
    build = {
        'sort_line': line,
        'build_string': build_string,
        'build_spacing': build_spacing,
        'ok': False,
        'warnings': False,
        'errors': False,
        'error_log_html': ''
    }

    if 'OK' in line:
        build['ok'] = True
    elif 'WARNINGS' in line:
        build['warnings'] = True
    elif '[ERRORS]' in line:
        # delete bad firmware, since it is still there when it is too large
        implied_firmware_name = line.split()[1].replace(':', '_').replace('/', '_')
        implied_firmware_glob = glob.glob(f'{Path(vial_dir, implied_firmware_name)}.*')
        for file_path in implied_firmware_glob:
            Path(file_path).unlink()
            try:
                template_data['fw_files'].remove(PurePath(file_path).name)
            except ValueError:
                log.error("Could not remove %s from fw_files list", PurePath(file_path).name)

        # document failure
        errored_board = line.split()[1].split(':')[0]
        individual_build_output = \
            docker_cmd_stdout(container_id, f'qmk compile -kb {errored_board} -km vial')
        html = conv.convert(individual_build_output)
        with open(Path(vial_dir, f'{implied_firmware_name}.html'),
                  'w', encoding="utf-8") as error_file:
            error_file.write(html)

        build['errors'] = True
        build['error_log_html'] = f'{implied_firmware_name}.html'
    template_data['builds'].append(build)


if __name__ == "__main__":
    main()
