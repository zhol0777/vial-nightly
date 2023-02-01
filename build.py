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

from copy import deepcopy
from pathlib import Path, PosixPath, PurePath
from threading import Thread

from ansi2html import Ansi2HTMLConverter
from jinja2 import Template

from docker_interface import docker_cmd_stdout, docker_run_cmd, close_containers, prepare_container
from util import FIRMWARE_TAR, PAGE_HEADER, PAGE_CHAR_WIDTH, freshness_check


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    '''Parse two arguments, one for debug mode, other to just remember to close containers'''
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true')
    parser.add_argument('--force', '-f', action='store_true', default=False)
    parser.add_argument('-close-docker-containers', '-cdc', action='store_true')
    parser.set_defaults(debug=False, close_docker_containers=False)
    args = parser.parse_args()
    return args


def compile_within_container(args: argparse.Namespace, container_id: str) -> str:
    '''Run commands to compile all vial fw within container provided'''
    # thank you piginzoo for showing me what i did wrong here
    docker_run_cmd(args, container_id, 'exec', 'python3 -m pip install -r /qmk_firmware/requirements.txt')
    total_build_output = docker_cmd_stdout(args, container_id, 'qmk multibuild -j`nproc` -km vial',
                                           False)

    docker_run_cmd(args, container_id, 'exec', 'qmk clean')
    docker_run_cmd(args, container_id, 'exec', 'mkdir -p /vial')
    docker_run_cmd(args, container_id, 'exec',
                   "find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +")

    return total_build_output


def process_build_output(args: argparse.Namespace, line: str, vial_dir: Path, container_id: str,
                         template_data: dict, rules_mk_file_list: list) -> None:
    '''Build the list of build lines and thread each build'''
    conv = Ansi2HTMLConverter(dark_bg=True)
    # line example:
    # Build kbdfans/kbd67/mkiirgb/v3:vial                                     [WARNINGS]
    build_string = ' '.join(line.split()[0:2])  # Build kbdfans/kbd67/mkiirgb/v3:vial
    build_spacing = ' ' * (PAGE_CHAR_WIDTH - len(build_string))
    build = {
        'sort_line': line,
        'build_string': build_string,
        'build_spacing': build_spacing,
        'ok': False,
        'warnings': False,
        'errors': False,
        'error_log_html': '',
        'rules_mk_html': ''
    }

    # provide rules.mk info
    log_rules_mk_per_firmware(args, line, vial_dir, container_id, conv, build, rules_mk_file_list)

    if '[ERRORS]' in line:
        process_compilation_error(args, line, vial_dir, container_id, conv, build, template_data)
    else:
        if 'OK' in line:
            build['ok'] = True
        elif 'WARNINGS' in line:
            build['warnings'] = True
    template_data['builds'].append(build)


def log_rules_mk_per_firmware(args: argparse.Namespace, line: str, vial_dir: Path,
                              container_id: str, conv: Ansi2HTMLConverter, build: dict,
                              rules_mk_file_list: list) -> None:
    '''find rules.mk for each build and generate html accordingly'''
    # kbdfans_kbd67_mkiirgb_v3_vial
    implied_firmware_name = line.split()[1].replace(':', '_').replace('/', '_')
    # ['kbdfans', 'kbd67', 'mkiirgb', 'v3']
    subdirs = line.split()[1].split(':')[0].split('/')

    # filter total list down to one list based on subdirs
    for subdir in subdirs:
        new_rules_mk_file_list = list(filter(lambda path, sd=subdir: (sd in path),  # type: ignore
                                             rules_mk_file_list))
        if len(new_rules_mk_file_list) == 0:
            # if odd possibility that the vial rules.mk doesn't exist somewhere in that subdir, bail
            continue
        else:
            rules_mk_file_list = new_rules_mk_file_list  # type: ignore
        if len(rules_mk_file_list) == 1:
            # qmkfm basecontainer is debian, hence, forced posixpath
            build['rules_mk_html'] = generate_rules_mk_html(args, container_id,
                                                            conv, implied_firmware_name,
                                                            rules_mk_file_list[0],  # type: ignore
                                                            vial_dir)
            continue
    if not build['rules_mk_html']:
        # at this point, rules_mk_file_list should be shrunk down enough to deal with ambiguity
        # to where we are, for ex. comparing subdirs
        # ['argo_works', 'ishi', '80', 'mk0_avr', 'vial'] to
        # [./keyboards/argo_works/ishi/80/mk0_avr_extra/keymaps/vial/rules.mk,
        #  ./keyboards/argo_works/ishi/80/mk0_avr/keymaps/vial/rules.mk]
        # so we can do a bit of obvious filtering
        for possible_rules_mk in rules_mk_file_list:
            shared_dirs = set.intersection(set(subdirs), set(possible_rules_mk.split('/')))
            if len(shared_dirs) == len(subdirs):
                build['rules_mk_html'] = \
                    generate_rules_mk_html(args, container_id, conv, implied_firmware_name,
                                           possible_rules_mk, vial_dir)
        if not build['rules_mk_html']:
            log.error("Could not find rules.mk correctly for %s! Filtered paths are %s",
                      implied_firmware_name, rules_mk_file_list)


def generate_rules_mk_html(args: argparse.Namespace, container_id: str,
                           conv: Ansi2HTMLConverter, implied_firmware_name: str,
                           rules_mk_file_path: str, vial_dir: Path) -> str:
    '''provide the file path for an html that contains rules.mk for some firmware'''
    # qmkfm basecontainer is debian, hence, forced posixpath
    rules_mk_file = PosixPath('/qmk_firmware') / rules_mk_file_path  # type: ignore
    rules_mk_content = docker_cmd_stdout(args, container_id, f'cat {rules_mk_file}')
    rules_mk_html = conv.convert(rules_mk_content)
    with open(Path(vial_dir, f'{implied_firmware_name}_rules.html'),
              'w', encoding="utf-8") as open_rules_mk_file:
        open_rules_mk_file.write(rules_mk_html)
    return f'{implied_firmware_name}_rules.html'


def process_compilation_error(args: argparse.Namespace, line: str, vial_dir: Path,
                              container_id: str, conv: Ansi2HTMLConverter,
                              build: dict, template_data: dict, ) -> None:
    '''Rebuild firmware that failed to compile properly, and log the build failure'''
    # delete bad firmware, since it is still there when it is too large
    implied_firmware_name = line.split()[1].replace(':', '_') \
        .replace('/', '_')
    implied_firmware_glob = glob.glob(f'{Path(vial_dir, implied_firmware_name)}.*')
    for file_path in implied_firmware_glob:
        Path(file_path).unlink()
        try:
            template_data['fw_files'].remove(PurePath(file_path).name)
        except ValueError:
            log.error("Could not remove %s from fw_files list",
                      PurePath(file_path).name)

    # document failure
    errored_board = line.split()[1].split(':')[0]
    individual_build_output = \
        docker_cmd_stdout(args, container_id,
                          f'qmk compile -kb {errored_board} -km vial',
                          False)
    html = conv.convert(individual_build_output)
    with open(Path(vial_dir, f'{implied_firmware_name}_errors.html'),
              'w', encoding="utf-8") as error_file:
        error_file.write(html)

    build['errors'] = True
    build['error_log_html'] = f'{implied_firmware_name}_errors.html'


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

    git_commit_id, fresh = freshness_check(cwd)
    if fresh and not args.force:
        log.error("Local files are implied to be fresh still!")
        sys.exit(1)

    container_id = prepare_container(args)
    git_log = docker_cmd_stdout(args, container_id, 'git log --decorate')
    git_log = git_log.replace('<', '(')
    git_log = git_log.replace('>', ')')
    template_data = {
        'page_header': PAGE_HEADER,
        'git_commit_id': git_commit_id,
        'build_time': subprocess.check_output("date", shell=True,
                                              encoding='utf8'),
        'git_log': git_log,
        'builds': [],
        'fw_files': []
    }

    total_build_output = compile_within_container(args, container_id)

    log.info("Copying tarball to local")
    subprocess.run(f'docker cp {container_id}:/vial -> {FIRMWARE_TAR}',
                   shell=True, stdout=subprocess.DEVNULL, check=True)

    # prepare serving for creation/refresh
    Path('vial').mkdir(exist_ok=True)

    # this has no subdirectories, so no need to recurse
    for dir_file in vial_dir.iterdir():
        try:
            dir_file.unlink()
        except IsADirectoryError:
            # wow looks like you left a folder in here!
            log.exception("Could not unlink %s due to it not being a file",
                          dir_file)
    template_path = Path(cwd, 'templates', 'template.html.jinja')
    html_template = Template(template_path.read_text(encoding='utf8'),
                             trim_blocks=True, lstrip_blocks=True)

    log.info("Untar tarball")
    subprocess.run(f'tar -xvf {FIRMWARE_TAR}', shell=True,
                   stdout=subprocess.DEVNULL, check=True)
    Path(cwd, FIRMWARE_TAR).unlink()

    for fw_file in vial_dir.iterdir():
        template_data['fw_files'].append(fw_file.name)
    template_data['fw_files'].sort()

    rules_mk_file_list = \
        docker_cmd_stdout(args, container_id,
                          'find -name rules.mk | grep /vial/').split('\n')
    open_threads: list[Thread] = []
    for line in total_build_output.split('\n'):
        if line:
            new_thread = Thread(target=process_build_output,
                                args=(args, line, vial_dir, container_id,
                                      template_data,
                                      deepcopy(rules_mk_file_list)))
            open_threads.append(new_thread)
            new_thread.start()

    for open_thread in open_threads:
        open_thread.join()

    template_data['builds'] = sorted(template_data['builds'],
                                     key=lambda d: d['sort_line'])

    index_html_path = Path(vial_dir, 'index.html')
    with open(index_html_path, 'w', encoding='utf8') as index_html:
        index_html.write(html_template.render(template_data))

    shutil.copyfile(Path(cwd, 'favicon.ico'),
                    Path(vial_dir, 'favicon.ico'))

    if not args.debug:
        close_containers(container_id)


if __name__ == "__main__":
    main()
