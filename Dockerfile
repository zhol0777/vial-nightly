FROM python:3.13-trixie

RUN apt update && apt install --no-install-recommends -y \
    sudo

RUN git clone --depth=5 https://github.com/vial-kb/vial-qmk.git /qmk_firmware
RUN pip install qmk
WORKDIR /qmk_firmware

# What do you want to do?
#         1. Delete and reclone qmk/qmk_firmware
#         2. Delete and clone a different fork
#         3. Keep it and continue
SHELL ["/bin/bash", "-c"]
RUN yes 3 | qmk setup -y -H /qmk_firmware

# make sure dependencies installed correctly
RUN qmk compile -kb mkh_studio/bully -km vial
