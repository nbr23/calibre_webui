#! /usr/bin/env sh

set -e

# Download required web frontend libraries
mkdir -p calibre_webui/static/css/ && mkdir calibre_webui/static/js/
wget -q https://code.jquery.com/jquery-3.6.0.min.js -O calibre_webui/static/js/jquery.min.js
wget -q https://github.com/twbs/bootstrap/releases/download/v4.6.2/bootstrap-4.6.2-dist.zip -O bootstrap.zip
unzip -jo bootstrap.zip *.css *.css.map -d calibre_webui/static/css/
unzip -jo bootstrap.zip *.js *.js.map -d calibre_webui/static/js/
rm -f bootstrap.zip
