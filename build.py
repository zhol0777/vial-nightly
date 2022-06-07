#!/usr/bin/python3

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

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true')
    parser.set_defaults(debug=False)
    args = parser.parse_args()
    return args


def docker_run_cmd(args: argparse.Namespace, container_id: str, cmd: str, line: str = None):
    try:
        subprocess_cmd = f'docker {cmd} {container_id} {line}'
        log.info('Running: %s', subprocess_cmd)
        subprocess.run(subprocess_cmd, shell=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        print(e)
        if not args.debug:
            close_containers(args, container_id)(args, container_id)
        exit(1)


def docker_cmd_stdout(container_id: str, line: str):
    proc = subprocess.run(f'docker exec {container_id} {line}', shell=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding='utf8')
    return proc.stdout


def close_containers(container_id: str):
    subprocess.run(f'docker stop {container_id}', shell=True)
    subprocess.run(f'docker container rm {container_id}', shell=True)


def main():
    args = parse_args()
    cwd = os.getcwd()

    if args.debug:
        container_id = 'vial'
    else:
        try:
            create_container_command = f'docker run -dit --name vial --workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
            container_id = subprocess.check_output(create_container_command, shell=True, encoding='utf8').strip()
        except subprocess.CalledProcessError:
            exit(125)
    exec_prefix = f'docker exec {container_id}'
        
    if not args.debug:
        docker_run_cmd(args, container_id, 'exec', f'git clone --depth=5 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
        docker_run_cmd(args, container_id, 'exec', 'make git-submodule')
    
    # thank you piginzoo for showing me what i did wrong here
    total_build_output = docker_cmd_stdout(container_id, f'qmk multibuild -j`nproc` -km vial')

    docker_run_cmd(args, container_id, 'exec', 'qmk clean')
    docker_run_cmd(args, container_id, 'exec', 'mkdir -p /vial')
    docker_run_cmd(args, container_id, 'exec', "find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +")

    subprocess.run(f'docker cp {container_id}:/vial -> vial-files.tar', shell=True, stdout=subprocess.DEVNULL) 
    
    # prepare directories for creation/refresh
    for directory_needed in ['vial', 'error_pages']:
        try:
            os.mkdir(os.path.join(cwd, directory_needed))
        except FileExistsError:
            pass
        subprocess.run(f'rm {directory_needed}/* || true', shell=True,
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    
    subprocess.run('tar -xvf vial-files.tar', shell=True, stdout=subprocess.DEVNULL)
    subprocess.run('rm vial-files.tar', shell=True, stdout=subprocess.DEVNULL)

    conv = Ansi2HTMLConverter(dark_bg=True)

    commit_id = docker_cmd_stdout(container_id, 'git rev-parse HEAD').strip()
    head_commit = f'Commit: ({commit_id})\n'
    build_time_string = subprocess.check_output("date", shell=True, encoding='utf8')
    build_date = f'Build time: {build_time_string}'
    if args.debug:
        git_log = docker_cmd_stdout(container_id, 'git log HEAD --decorate')
    else:
        git_log = docker_cmd_stdout(container_id, 'git log HEAD~4 --decorate')

    # hacky way to flag breaks in
    index_html_contents = conv.convert(''.join([PAGE_HEADER, head_commit, build_date, git_log + '\nSEMAPHORE\n', total_build_output]))

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
            individual_build_output = docker_cmd_stdout(container_id, f'qmk compile -kb {errored_board} -km vial')
            html = conv.convert(individual_build_output)
            with open(os.path.join(cwd, 'error_pages', f'{implied_firmware_name}.html'), 'w') as wf:
                wf.write(html)

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
    index_html_contents = index_html_contents.replace(git_log,
        f'{git_log}\n<hr>\n')
    index_html_contents = index_html_contents.replace('class="ansi2html-content"',
        f'class="ansi2html-content" style="float:left"')
    index_html_contents = index_html_contents.replace('SEMAPHORE', '<hr>')


    with open(index_html_path, 'w+') as index_html:
        index_html.write(index_html_contents)

    if not args.debug:
        close_containers(container_id)

    subprocess.run('cp favicon.ico vial/', shell=True, stdout=subprocess.DEVNULL)

main()
