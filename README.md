# vial-nightly

Not much here. Run `build.sh` as a cronjob and get Apache to serve the `vial` directory.

This script downloads `ansi2html.sh` to do heavy lifting, so don't run this until you can audit that script.
* `ansi2html.sh` requires `gawk` installed, so be sure to have that installed too.

Made with pointers from looking at Github Actions from xelus22's [QMK-VIA-HEX](https://github.com/Xelus22/QMK-VIA-Hex).