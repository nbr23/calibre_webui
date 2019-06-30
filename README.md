Calibre WebUI
=============

A simple web ui for the [Calibre](https://calibre-ebook.com/) ebook conversion
and library tool.

Installation
------------

### Dependencies

- [Calibre](https://calibre-ebook.com/): Calibre-webui depends on Calibre to
  be installed on the system as it operates as a front-end to it.
- [Redis](https://redis.io/): Redis is used for background task message
  communication management.
- Python 3.7 (Not tested with lower versions)
- Python requirements can be installed with:
`pip install -r requirements.txt`

### uWSGI

Create a uWSGI configuration file, eg:

```
[uwsgi]
master = true
processes = 5

uid = calibre
socket = /var/run/calibre/calibre_webui.sock
chmod-socket = 660
vacuum = true
die-on-term = true
logto = /var/log/calibre/error.log
log-5xx = true
disable-logging = true
enable-threads = true

mount = /=calibre_webui:app
```

Make sure threads are enabled, or conversion tasks will not run.

### nginx

It is preferred to use a full httpd to serve calibre-webui, rather than
exposing uWSGI directly:

```
location / {
    include uwsgi_params;
    uwsgi_pass unix:/var/run/calibre/calibre_webui.sock;
}
```

The static files (in /calibre-webui/static) should be served through your
httpd.

### systemd

Finally, you may want to run calibre-webui using systemd. More information is
available on [uWSGI's
documentation](https://uwsgi-docs.readthedocs.io/en/latest/Systemd.html).
If using a virtualenv, make sure to activate it in your execution command.

Configuration
-------------

Edit the `calibre_webui/calibre_webui.cfg` file and set at least:
- `CALIBRE_LIBRARY_PATH`: Set to the path of an existing Calibre library. The
  directory *must* contain the metadata.db file
- `APP_SECRET_KEY`: to a random string
- `REDIS_HOST`: to the host running your redis DB (typically localhost if
  running locally)
- `STATIC_URL`: to the url where your static files are hosted (jquery,
  bootstrap)

Docker
------

For ease of use, calibre_webui can be deployed using docker.

### Configuration
Before anything, make sure to edit `calibre_webui/calibre_webui.cfg` and set:
- `APP_SECRET_KEY`: to a random string
- `STATIC_URL`: to the url where your static files are hosted (jquery,
  bootstrap)

The variables `CALIBRE_LIBRARY_PATH`, `CALIBRE_TEMP_DIR`,
`CALIBRE_WEBUI_DB_PATH` and `REDIS_HOST` have been preset for Docker use.

You will also need to update the docker-compose.yml file to update the *source*
of the calibre_library volume to point to a host directory where your library
is or will be stores, for example as follows:
```
volumes:
  - type: bind
  source: /mnt/nfs_share/books
  target: /data/calibre_library
```

### nginx
The container will now listen on a tcp socket on port 8000, use an nginx
configuration based on the following to server the content:
```
server {
  listen 80 default_server;
  listen [::]:80;


  root /var/www/html;

  index index.html index.htm index.nginx-debian.html;

  server_name calibre.example.com;

  location / {
    include uwsgi_params;
    uwsgi_pass localhost:8000;
  }
}
```

Note: it is advised to increase your
[client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)
in nginx, as you will most likely be uploading large files to calibre_webui
(the default being
1M).
