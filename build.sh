#!/bin/bash

set -e

python3 ./build.py $1

head -n -2 index.html > ./vial/index.html

# this is lifted from qmk.tzarc.io
echo "<div style='position:absolute; right:0; top:0; padding: 1em; border-left: 1px solid #666; border-bottom: 1px solid #666'\>" >> ./vial/index.html
echo "<pre>" >> ./vial/index.html

# provide download links per page
for file in vial/*; do
    base_file_name=$(basename $file)
    echo "<b><a style='color:#FAED27' href='$base_file_name'>$base_file_name</a></b>" >> ./vial/index.html
done;

echo "</pre\>" >> ./vial/index.html
echo "</div\>" >> ./vial/index.html
echo "</body\>" >> ./vial/index.html
echo "</html\>" >> ./vial/index.html

for file in error_pages/*; do
    mv $file vial/
done;

cp favicon.ico vial/
