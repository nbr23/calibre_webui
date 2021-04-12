Calibre WebUI
=============

A simple web ui for the [Calibre](https://calibre-ebook.com/) ebook conversion
and library tool.

Installation
------------

### Ansible

The role
[ansible-role-calibrewebui](https://github.com/nbr23/ansible-role-calibrewebui)
can be used for easy deployment using docker and nginx.

### Dependencies

- [Calibre](https://calibre-ebook.com/): Calibre-webui depends on Calibre to
  be installed on the system as it operates as a front-end to it.
- Python 3.7 (Not tested with lower versions)
- Python requirements can be installed with:
`pip install -r requirements.txt`

### uWSGI

Update the uWSGI configuration file `calibre_webui.ini` to fit your need.

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

### systemd

Finally, you may want to run calibre-webui using systemd. More information is
available on [uWSGI's
documentation](https://uwsgi-docs.readthedocs.io/en/latest/Systemd.html).
If using a virtualenv, make sure to activate it in your execution command.

Configuration
-------------

All configuration variables defaults and descriptions can be found in
[calibre_webui/default_config.py](https://github.com/nbr23/calibre_webui/blob/master/calibre_webui/default_config.py).

You can set and overwrite these variables by setting them in a similarly
formatted file under `/etc/calibre_webui/calibre_webui.cfg`.

It is required to set at least the following variables:
- `CALIBRE_LIBRARY_PATH`: Set to the path of an existing Calibre library. The
  directory *must* contain the metadata.db file
- `APP_SECRET_KEY`: to a random string

Docker
------

For ease of use, calibre_webui can be deployed using docker.

### Configuration

Create your local `calibre_webui.cfg` file setting at least:

- `APP_SECRET_KEY`: to a random string

The variables `CALIBRE_LIBRARY_PATH`, `CALIBRE_TEMP_DIR`,
`CALIBRE_WEBUI_DB_PATH` defaults have been preset for Docker use.

Then bind it in your docker-compose to `/etc/calibre_webui/calibre_webui.cfg`:

```
services:
  app:
    [...]
    volumes:
    - ./calibre_webui.cfg:/etc/calibre_webui/calibre_webui.cfg:ro
```

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
