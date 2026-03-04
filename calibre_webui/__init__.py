import os
from flask import Flask
from flask_qrcode import QRcode

from calibre_webui.calibre_webui_db import CalibreWebUIDB
from calibre_wrapper.calibredb import CalibreDBW

app = Flask(__name__)
qrcode = QRcode(app)

#app.config.from_pyfile('defaults.py', silent=True)
app.config.from_object('calibre_webui.default_config')

if os.path.isfile('/etc/calibre_webui/calibre_webui.cfg'):
    app.config.from_pyfile('/etc/calibre_webui/calibre_webui.cfg', silent=True)

import calibre_webui.default_config as _default_config
for _key in dir(_default_config):
    if not _key.startswith('_') and _key in os.environ:
        app.config[_key] = os.environ[_key]

if not app.config.get('APP_SECRET_KEY'):
    raise RuntimeError('APP_SECRET_KEY is not set')
app.secret_key = app.config['APP_SECRET_KEY']
app.FLASH = {'error': 'danger',
        'warning': 'warning',
        'success': 'success',
        'debug': 'info'}

app.calibredb_wrap = CalibreDBW(app.config)
app.database = CalibreWebUIDB(app.config)

from calibre_webui import routes
