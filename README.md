# vial-nightly

## What is this?

This builds firmware for every keyboard with vial keymap support in [vial-qmk](https://github.com/vial-kb/vial-qmk/),
a fork of qmk, and gives you a folder of the firmware binaries. Since all the building is done
within qmkfm/base_container, the only major dependencies are docker, python3, and a python package.

## How do I use this?

I run `build.py` as a cronjob and get Apache to serve the `vial` directory, but you can use whatever server to serve
the directory of files. This implies that you already have docker installed, and the user that runs docker is a member
of the `docker` group, or is root.

I have python 3.7 on the server this script runs on, so that should probably work. Be sure to install the dependencies
in `dependencies.txt` using your preferred installation method.

Made with pointers from looking at Github Actions from xelus22's [QMK-VIA-HEX](https://github.com/Xelus22/QMK-VIA-Hex).

# TODO

* Make index.html look better
  * Ape qmk.tzarc.io's design less
    * sorry, tzarc
