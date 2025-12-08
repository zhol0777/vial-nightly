# vial-nightly

## What is this?

This builds firmware for every keyboard with vial keymap support in [vial-qmk](https://github.com/vial-kb/vial-qmk/),
a fork of qmk, and gives you a folder of the firmware binaries. Since all the building is done
within qmkfm/base_container, the only major dependencies are docker, python3, and a python package.

Made with pointers from looking at Github Actions from xelus22's [QMK-VIA-HEX](https://github.com/Xelus22/QMK-VIA-Hex).

## How do I use this?

You'll need two cronjobs -
* One to build the docker image - a [change](https://github.com/python/cpython/issues/119562) to the ast library
deployed in Python 3.14 hasn't had the corresponding fixes propagate to the qmk_cli docker image, so you have to
build this custom one pinned to python 3.13. You can probably just run this monthly, as `build.py` pulls up latest
git changes.
* One to run `build.py`.

I run `build.py` as a cronjob and get Caddy to serve the `vial` directory, but you can use whatever server to serve
the directory of files. This implies that you already have docker installed, and the user that runs docker is a member
of the `docker` group, or is root.


## Why do I use this?

I had a spare domain name I wanted to use.

Firmware blobs for boards hidden on discords are annoying to find, and so is setting up a QMK dev environment if
you're not especially tech-savvy, so I set this up for my friends to pull FW from. But, you also don't have to!
okin#3938 hosts [a similar solution](https://gitlab.com/okin/vial-qmk-firmwares)
[here](https://okin.gitlab.io/vial-qmk-firmwares/), if you are more inclined to use SaaS CI sorts of stuff.

## TODO

* Make index.html look better
  * Ape qmk.tzarc.io's design less
    * sorry, tzarc
* ~~List state of `rules.mk` for each fw to indicate which features need to be disabled~~
  * Then think of a way to present it in a decent way
* ~~Mount git repo from a specifc folder on host instead of on container fs~~
* recognize when to error out and prevent writing to `.commit_id` if job fails
