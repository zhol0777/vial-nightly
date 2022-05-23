#!/bin/bash

set -ex

mkdir -p vial
wget https://raw.githubusercontent.com/pixelb/scripts/master/scripts/ansi2html.sh
chmod +x ansi2html.sh

vial=$(docker run -dit --name vial --workdir /qmk_firmware qmkfm/base_container)
docker exec $vial git clone --depth=1 https://github.com/vial-kb/vial-qmk /qmk_firmware
docker exec $vial make git-submodule
(docker exec $vial qmk multibuild -j`nproc` -km vial) | sh ./ansi2html.sh > output.html
docker exec $vial qmk clean
docker exec $vial mkdir /vial
docker exec $vial find /qmk_firmware -name '*_vial.*' -exec mv -t /vial {} +

docker cp $vial:/vial - > vial-files.tar
docker stop $vial
docker container rm $vial

rm vial/* || true
tar -xvf vial-files.tar
rm vial-files.tar

for file in vial/*; do
    mv $file ${file%.*}.$(date -I).${file#*.};
done;

# prepare stuff for apache

head -n -2 output.html > index.html

sed -i '271s/000000/FFFFFF/' index.html
sed -i '272s/FFFFFF/000000/' index.html

echo "<div style='position:absolute; right:0; top:0; padding: 1em; border-left: 1px solid #666; border-bottom: 1px solid #666' class=\"f9 b9\"\>" >> index.html
echo "<pre>" >> index.html

for file in vial/*; do
    base_file_name=$(basename $file)
    echo "<a href='$base_file_name'>$base_file_name</a>" >> index.html
done;

echo "</pre\>" >> index.html
echo "</div\>" >> index.html
echo "</body\>" >> index.html
echo "</html\>" >> index.html

mv index.html vial/
cp favicon.ico vial/
