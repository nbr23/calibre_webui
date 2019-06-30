#! /usr/bin/env bash

# If the library database doesn't exist, we create an empty one
if ! [ -f /data/calibre_library/metadata.db ]; then
  cat /usr/share/calibre/metadata_sqlite.sql | sqlite3 /data/calibre_library/metadata.db;
  chown calibre:www-data /data/calibre_library/metadata.db;
fi

# Then run the Flask app
cd /var/www/calibre_webui
uwsgi --ini calibre_webui.ini
