#!/bin/bash

set -ex

mkdir -p vial

vial=$(docker run -dit --name vial --workdir /qmk_firmware qmkfm/base_container)
docker exec $vial git clone https://github.com/vial-kb/vial-qmk /qmk_firmware
docker exec $vial make git-submodule
docker exec $vial qmk multibuild -j`nproc` -km vial || true
docker exec $vial qmk clean
docker exec $vial mkdir /vial
docker exec $vial find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +

docker cp $vial:/vial - > vial-files.tar
docker stop $vial
docker container rm $id

rm vial/*
tar -xvf vial-files.tar
rm vial-files.tar

for file in vial/*; do mv $file ${file%.*}.$(date -I).${file#*.}; done;

