# vial-nightly

## What is this?

This builds firmware for every keyboard with vial keymap support in [vial-qmk](https://github.com/vial-kb/vial-qmk/), a fork of qmk, and gives you a folder of the firmware binaries. Since all the building is done within qmkfm/base_container, no dependencies beyond docker and gawk are needed.

## How do I use this?

I run `build.sh` as a cronjob and get Apache to serve the `vial` directory, but you can use whatever server to serve the directory of files. This implies that you already have docker installed, and the user that runs docker is a member of the `docker` group, or is root.

This script downloads `ansi2html.sh` to do heavy lifting, so don't run this until you can audit that script.
* `ansi2html.sh` requires `gawk` installed, so be sure to have that installed too.

Made with pointers from looking at Github Actions from xelus22's [QMK-VIA-HEX](https://github.com/Xelus22/QMK-VIA-Hex).

# TODO
* Generating index.html should probably be done with something like beautifulsoup instead of shell i/o redirection.
* Make index.html look better
  * For every board that fails to compile, provide output from `make` for why 
