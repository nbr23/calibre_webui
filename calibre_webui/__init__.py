from flask import Flask
from flask_qrcode import QRcode

from calibre_webui.calibre_webui_db import CalibreWebUIDB
from calibre_wrapper.calibredb import CalibreDBW

app = Flask(__name__)
qrcode = QRcode(app)

app.config.from_pyfile('calibre_webui.cfg', silent=True)
app.secret_key = app.config['APP_SECRET_KEY']
app.FLASH = {'error': 'danger',
        'warning': 'warning',
        'success': 'success',
        'debug': 'info'}

app.calibredb_wrap = CalibreDBW(app.config)
app.database = CalibreWebUIDB(app.config)

from calibre_webui import routes
