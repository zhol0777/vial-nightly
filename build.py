#!/usr/bin/python3

'''
Mostly just builds vial firmware blobs and does some organizing and touching up index.html
and build.sh should handle the rest
# TODO: make build.py handle all the stuff build.sh still has left
'''

import argparse
import logging
import os
import subprocess

from ansi2html import Ansi2HTMLConverter

VIAL_GIT_URL = 'https://github.com/vial-kb/vial-qmk'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/base_container'
ERROR_FLAG = '[ERRORS]'
PAGE_HEADER = 'vial-qmk nightly\n'
SEMAPHORE = 'SEMAPHORE'

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


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
        subprocess.run(subprocess_cmd, shell=True, stdout=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        log.exception("Exception raised by failure to run command in docker")
        if not args.debug:
            close_containers(container_id)
        exit(1)


def docker_cmd_stdout(container_id: str, line: str):
    '''Frontend to simplify getting stdout from docker command'''
    proc = subprocess.run(f'docker exec {container_id} {line}', shell=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding='utf8', check=False)
    return proc.stdout


def close_containers(container_id: str):
    '''Close qmkfm/basecontainer docker containers when needed'''
    subprocess.run(f'docker stop {container_id}', shell=True, check=True)
    subprocess.run(f'docker container rm {container_id}', shell=True, check=True)


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
        exit(0)

    cwd = os.getcwd()

    if args.debug:
        container_id = 'vial'
    else:
        try:
            create_container_command = \
                f'docker run -dit --name vial --workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
            container_id = subprocess.check_output(create_container_command,
                                                   shell=True, encoding='utf8').strip()
        except subprocess.CalledProcessError:
            exit(125)

    if not args.debug:
        docker_run_cmd(args, container_id, 'exec',
                       f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')

    # thank you piginzoo for showing me what i did wrong here
    total_build_output = docker_cmd_stdout(container_id, 'qmk multibuild -j`nproc` -km vial')

    docker_run_cmd(args, container_id, 'exec', 'qmk clean')
    docker_run_cmd(args, container_id, 'exec', 'mkdir -p /vial')
    docker_run_cmd(args, container_id, 'exec',
                   "find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +")

    subprocess.run('docker cp {container_id}:/vial -> vial-files.tar', shell=True,
                   stdout=subprocess.DEVNULL, check=True)

    # prepare directories for creation/refresh
    for directory_needed in ['vial', 'error_pages']:
        try:
            os.mkdir(os.path.join(cwd, directory_needed))
        except FileExistsError:
            pass
        subprocess.run(f'rm {directory_needed}/*', shell=True,
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=False)

    subprocess.run('tar -xvf vial-files.tar', shell=True, stdout=subprocess.DEVNULL, check=True)
    subprocess.run('rm vial-files.tar', shell=True, stdout=subprocess.DEVNULL, check=True)

    conv = Ansi2HTMLConverter(dark_bg=True)

    commit_id = docker_cmd_stdout(container_id, 'git rev-parse HEAD').strip()
    head_commit = f'Commit: ({commit_id})\n'
    build_time_string = subprocess.check_output("date", shell=True, encoding='utf8')
    build_date = f'Build time: {build_time_string}'
    git_log = docker_cmd_stdout(container_id, 'git log --decorate')

    # hacky way to flag breaks in
    index_html_contents = conv.convert(''.join([PAGE_HEADER, head_commit, build_date, git_log,
                                                SEMAPHORE, total_build_output]))

    for line in total_build_output.split('\n'):
        if ERROR_FLAG in line:
            # usually formatted as "Build some/board/here:vial ... [ERRORS]"
            build_status_string = ' '.join(line.split()[0:2])

            # delete bad firmware, since it is still there when it is too large
            implied_firmware_name = line.split()[1].replace(':', '_').replace('/', '_')
            implied_firmware_path = os.path.join(cwd, 'vial', implied_firmware_name)
            subprocess.Popen(f'rm {implied_firmware_path}*', shell=True)

            # document failure
            errored_board = line.split()[1].split(':')[0]
            individual_build_output = \
                docker_cmd_stdout(container_id, f'qmk compile -kb {errored_board} -km vial')
            html = conv.convert(individual_build_output)
            with open(os.path.join(cwd, 'error_pages', f'{implied_firmware_name}.html'),
                                   'w', encoding="utf-8") as error_file:
                error_file.write(html)

            # link to failure
            index_html_contents = index_html_contents.replace(ERROR_FLAG,
                f'<a class=\'ansi31\' href={implied_firmware_name}.html>{ERROR_FLAG}</a>')
            index_html_contents = index_html_contents.replace(build_status_string,
                f'<a class=\'ansi31\' href={implied_firmware_name}.html>{build_status_string}</a>')

    index_html_path = os.path.join(cwd, 'index.html')

    # last minute prettying up

    index_html_contents = index_html_contents.replace(PAGE_HEADER,
        f'<h1>{PAGE_HEADER}</h1>')
    index_html_contents = index_html_contents.replace(head_commit,
        f'<h2>{head_commit}</h2>')
    index_html_contents = index_html_contents.replace(build_date,
        f'<h2>{build_date}</h2>\n<hr>\n')
    index_html_contents = index_html_contents.replace('class="ansi2html-content"',
        'class="ansi2html-content" style="float:left"')
    index_html_contents = index_html_contents.replace(SEMAPHORE, '<hr>')

    with open(index_html_path, 'w+', encoding="utf-8") as index_html:
        index_html.write(index_html_contents)

    if not args.debug:
        close_containers(container_id)


if __name__ == "__main__":
    main()
