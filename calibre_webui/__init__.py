from flask import Flask
import redis
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

app.redis_queue = redis.Redis(app.config['REDIS_HOST'],
        charset="utf-8", decode_responses=True)
app.calibredb_wrap = CalibreDBW(app.config, app.redis_queue)
app.database = CalibreWebUIDB(app.config)

from calibre_webui import routes
