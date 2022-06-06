#!/usr/bin/python3

import os
import subprocess

from ansi2html import Ansi2HTMLConverter

VIAL_GIT_URL = 'https://github.com/vial-kb/vial-qmk'
QMK_FIRMWARE_DIR = '/qmk_firmware'
QMK_DOCKER_IMAGE = 'qmkfm/base_container'

def main():
    cwd = os.getcwd()
    try:
        os.mkdir(os.path.join(cwd, 'vial'))
    except FileExistsError:
        pass

    create_container_command = f'docker run -dit --name vial --workdir {QMK_FIRMWARE_DIR} {QMK_DOCKER_IMAGE}'
    container_id = subprocess.check_output(create_container_command, shell=True)

    exec_prefix = f'docker exec {container_id}'
    
    def docker_cmd(cmd: str, line: str = None):
        subprocess.check_call(f'docker {cmd} {container_id} {line}') 
    
    docker_cmd('exec', f'git clone --depth=1 {VIAL_GIT_URL} {QMK_FIRMWARE_DIR}')
    docker_cmd('exec', 'make git-submodule')
    
    # thank you piginzoo for showing me what i did wrong here
    build_cmd = subprocess.run(f'docker exec {container_id} qmk multibuild -j`nproc` -km vial',
                               shell=True, stdout=subprocess.PIPE, encoding='utf8')
    total_build_output = build_cmd.output

    docker_cmd('exec', 'qmk clean')
    docker_cmd('exec', 'mkdir /vial')
    docker_cmd('exec', "find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +")

    subprocess.check_call(f'docker cp {container_id}:/vial - > vial-files.tar') 
    subprocess.check_call('rm vial/* || true', shell=True)
    subprocess.check_call('tar -xvf vial-files.tar', shell=True)
    subprocess.check_call('rm vial-files.tar', shell=True)

    # alright i need to test this on actual hardware later
    errored_build_output_list = []
    for line in total_build_output.split('\n'):
        if '[ERRORS]' in line:
            # usually formatted as "Build some/board/here:vial ... [ERRORS]"
            # delete bad firmware
            implied_firmware_name = line.replace(':', '_').replace('/', '_')
            implied_firmware_path = os.path.join(cwd, implied_firmware_name)
            subprocess.Popen(['rm', f'{implied_firmware_path}*'], shell=True)

            # document failure
            errored_board = line.split()[1].split(':')[0]
            individual_build_cmd = subprocess.run(f'{exec_prefix} qmk compile -kb {errored_board} -km vial')
            errored_build_output_list.append(individual_build_cmd.output)

    conv = Ansi2HTMLConverter()
    concatenated_failed_build_output = "".join(errored_build_output_list)
    html = conv.convert(total_build_output + concatenated_failed_build_output)
    with open("index.html", 'w') as wf:
        wf.write(html)

    docker_cmd('stop')
    docker_cmd('container rm')

    subprocess.check_call('mv index.html vial/', shell=True)
    subprocess.check_call('cp favicon.ico vial/', shell=True)

main()
