#!/usr/bin/python3

'''
Mostly just builds vial firmware blobs and does some organizing and touching up index.html
'''

import argparse
import concurrent.futures
import glob
import logging
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path, PosixPath, PurePath

from ansi2html import Ansi2HTMLConverter
from docker.models.containers import Container
from jinja2 import Template

from docker_interface import close_containers, exec_run_wrapper, exec_run_wrapper_no_bail, prepare_container
from util import (
    PAGE_CHAR_WIDTH,
    PAGE_HEADER,
    BuildDict,
    TemplateDataDict,
    determine_worker_count,
    freshness_check,
    set_last_successful_build,
)

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    '''Parse two arguments, one for debug mode, other to just remember to close containers'''
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=False)
    parser.add_argument('--force', '-f', action='store_true', default=False)
    parser.add_argument('-close-docker-containers', '-cdc', action='store_true')
    parser.set_defaults(debug=False, close_docker_containers=False)
    args = parser.parse_args()
    return args


def compile_within_container(container: Container) -> str:
    '''Run commands to compile all vial fw within container provided'''
    # these take tons of machine time to compile and by many reports are broken
    exec_run_wrapper(container, 'rm -r keyboards/keychron')
    # thank you piginzoo for showing me what i did wrong here
    nproc = determine_worker_count()
    _, total_build_output = exec_run_wrapper(
        container, f'qmk mass-compile -j {nproc} -km vial')
    command_list = [
        'git stash',
        'qmk clean',
        'mkdir -p /vial',
        'find /qmk_firmware -maxdepth 1 -name "*_vial*" -exec mv -t /vial {} +'
        ]
    for cmd in command_list:
        exec_run_wrapper(container, cmd)

    return total_build_output


def process_build_output(line: str, vial_dir: Path,
                         container: Container,
                         template_data: TemplateDataDict,
                         rules_mk_file_list: list[str]) -> None:
    '''Build the list of build lines and thread each build'''
    conv = Ansi2HTMLConverter(dark_bg=True)
    # line example:
    # Build kbdfans/kbd67/mkiirgb/v3:vial                                     [WARNINGS]
    build_string = ' '.join(line.split()[0:2])  # Build kbdfans/kbd67/mkiirgb/v3:vial
    build_spacing = ' ' * (PAGE_CHAR_WIDTH - len(build_string))
    build: BuildDict = {
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
    log_rules_mk_per_firmware(line, vial_dir, container, conv, build, rules_mk_file_list)

    if '[ERRORS]' in line:
        process_compilation_error(line, vial_dir, container, conv, build, template_data)
    elif 'OK' in line:
        build['ok'] = True
    elif 'WARNINGS' in line:
        build['warnings'] = True
    template_data['builds'].append(build)


# pylint: disable=too-many-arguments
def log_rules_mk_per_firmware(line: str, vial_dir: Path,
                              container: Container,
                              conv: Ansi2HTMLConverter, build: BuildDict,
                              rules_mk_file_list: list[str]) -> None:
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
        rules_mk_file_list = new_rules_mk_file_list  # type: ignore
        if len(rules_mk_file_list) == 1:
            # qmkfm basecontainer is debian, hence, forced posixpath
            build['rules_mk_html'] = generate_rules_mk_html(container,
                                                            conv, implied_firmware_name,
                                                            rules_mk_file_list[0],  # type: ignore
                                                            vial_dir)
            continue
    if not build.get('rules_mk_html'):
        # at this point, rules_mk_file_list should be shrunk down enough to deal with ambiguity
        # to where we are, for ex. comparing subdirs
        # ['argo_works', 'ishi', '80', 'mk0_avr', 'vial'] to
        # [./keyboards/argo_works/ishi/80/mk0_avr_extra/keymaps/vial/rules.mk,
        #  ./keyboards/argo_works/ishi/80/mk0_avr/keymaps/vial/rules.mk]
        # so we can do a bit of obvious filtering
        for possible_rules_mk in rules_mk_file_list:
            shared_dirs: set[str] = set.intersection(set(subdirs), set(possible_rules_mk.split('/')))
            if len(shared_dirs) == len(subdirs):
                build['rules_mk_html'] = \
                    generate_rules_mk_html(container, conv, implied_firmware_name,
                                           possible_rules_mk, vial_dir)
        if not build.get('rules_mk_html'):
            log.error("Could not find rules.mk correctly for %s! Filtered paths are %s",
                      implied_firmware_name, rules_mk_file_list)


def generate_rules_mk_html(container: Container,
                           conv: Ansi2HTMLConverter, implied_firmware_name: str,
                           rules_mk_file_path: str, vial_dir: Path) -> str:
    '''provide the file path for an html that contains rules.mk for some firmware'''
    # qmkfm basecontainer is debian, hence, forced posixpath
    rules_mk_file = PosixPath('/qmk_firmware') / rules_mk_file_path  # type: ignore
    _, rules_mk_content = exec_run_wrapper(container, f'cat {rules_mk_file}', debug_log_output=False)
    rules_mk_html = conv.convert(rules_mk_content)
    with open(Path(vial_dir, f'{implied_firmware_name}_rules.html'),
              'w', encoding="utf-8") as open_rules_mk_file:
        open_rules_mk_file.write(rules_mk_html)
    return f'{implied_firmware_name}_rules.html'


# pylint: disable=too-many-arguments
def process_compilation_error(line: str, vial_dir: Path,
                              container: Container,
                              conv: Ansi2HTMLConverter,
                              build: BuildDict, template_data: TemplateDataDict) -> None:
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
    _, individual_build_output = exec_run_wrapper_no_bail(
        container, f'make {errored_board}:vial')
    html = conv.convert(individual_build_output)
    with open(Path(vial_dir, f'{implied_firmware_name}_errors.html'),
              'w', encoding="utf-8") as error_file:
        error_file.write(html)

    build['errors'] = True
    build['error_log_html'] = f'{implied_firmware_name}_errors.html'


# pylint: disable=too-many-locals
def main():
    '''
    Spin up docker container for qmkfm/qmk_cli
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
    if args.verbose:
        log.setLevel(logging.DEBUG)

    cwd = Path.cwd()
    vial_dir = Path(cwd, 'vial')

    git_commit_id, fresh = freshness_check(cwd)
    if fresh and not args.force:
        log.debug("Local files are implied to be fresh still!")
        sys.exit(1)

    container = prepare_container(args)
    _, git_log = exec_run_wrapper(container, 'git --no-pager log --decorate -n 5')
    git_log = git_log.replace('<', '(')
    git_log = git_log.replace('>', ')')

    template_data: TemplateDataDict = {
        'page_header': PAGE_HEADER,
        'git_commit_id': git_commit_id,
        'build_time': subprocess.check_output("date", shell=True, encoding='utf8'),
        'git_log': git_log,
        'builds': [],
        'fw_files': []
    }

    # prepare serving for creation/refresh
    Path('vial').mkdir(exist_ok=True)

    # this has no subdirectories, so no need to recurse
    for dir_file in vial_dir.iterdir():
        try:
            dir_file.unlink()
        except IsADirectoryError:  # noqa
            # wow looks like you left a folder in here!
            log.exception("Could not unlink %s due to it not being a file",
                          dir_file)
    total_build_output = compile_within_container(container)
    template_path = Path(cwd, 'templates', 'template.html.jinja')
    html_template = Template(template_path.read_text(encoding='utf8'),
                             trim_blocks=True, lstrip_blocks=True)

    for fw_file in vial_dir.iterdir():
        template_data['fw_files'].append(fw_file.name)
    template_data['fw_files'].sort()

    _, file_list_output = exec_run_wrapper(container, 'find -name rules.mk')
    rules_mk_file_list = [f for f in file_list_output.split('\n') if '/vial/' in f]

    max_workers = determine_worker_count()
    lines = [
        line for line in total_build_output.split('\n') if line and line.strip().startswith('Build ')
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                process_build_output,
                line, vial_dir, container, template_data, deepcopy(rules_mk_file_list)
            )
            for line in lines
        ]
        concurrent.futures.wait(futures)

    template_data['builds'] = sorted(template_data['builds'],
                                     key=lambda d: d['sort_line'])

    index_html_path = Path(vial_dir, 'index.html')
    with open(index_html_path, 'w', encoding='utf8') as index_html:
        index_html.write(html_template.render(template_data))

    shutil.copyfile(Path(cwd, 'favicon.ico'),
                    Path(vial_dir, 'favicon.ico'))

    if not args.debug:
        if container_id := getattr(container, 'id', None):
            close_containers(container_id)

    set_last_successful_build(cwd, git_commit_id)
    log.debug("Build complete!")


if __name__ == "__main__":
    main()
