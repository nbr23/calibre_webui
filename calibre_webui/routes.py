from flask import render_template, request, Response, send_from_directory, \
        jsonify, make_response, redirect, url_for, flash
from werkzeug.utils import secure_filename
from urllib.parse import urljoin
import os

from calibre_webui import app, qrcode
from calibre_wrapper.calibredb import CalibreDBW

def flash_error(message):
    return flash(message, app.FLASH['error'])

def flash_warning(message):
    return flash(message, app.FLASH['warning'])

def flash_debug(message):
    return flash(message, app.FLASH['debug'])

def flash_success(message):
    return flash(message, app.FLASH['success'])

# API Endpoints

@app.route('/api/books/list')
def get_books():
    page = int(request.args.get('page')) if 'page' in request.args else 1
    search = request.args.get("search").strip().lower() \
            if 'search' in request.args else None
    scope = request.args.get('search_scope').strip() \
            if 'search_scope' in request.args else None
    books = app.calibredb_wrap.search_books(search.lower() if search else None,
            scope.lower() if scope else None,
            page=page)
    if not books:
        return jsonify([])
    return jsonify([dict(book) for book in books])

@app.route('/api/books/<int:book_id>/formats')
def get_book_formats(book_id):
    return jsonify(app.calibredb_wrap.get_book_formats(book_id))

@app.route('/api/tasks/list')
def get_tasks_list():
    tasks = app.calibredb_wrap.list_tasks()
    return jsonify(tasks)

@app.route('/api/tasks/count')
def get_tasks_count():
    return jsonify(app.calibredb_wrap.tasks_count())

@app.route('/api/tasks/clear')
def clear_tasks():
    app.calibredb_wrap.clear_tasks()
    return jsonify({})

# File serving

@app.route('/js/<path:path>')
def static_js(path):
    return send_from_directory('static/js', path)

@app.route('/css/<path:path>')
def static_css(path):
    return send_from_directory('static/css', path)

@app.route('/img/<path:path>')
def static_img(path):
    return send_from_directory('static/img', path)

## Views ##

@app.route('/', methods=['GET'])
def index():
    search = request.args.get("search").strip().lower() \
            if 'search' in request.args else None
    scope = request.args.get('search_scope').strip() \
            if 'search_scope' in request.args else None
    return render_template('index.html', search=search,
            scope=scope, title='My Books', calibre_version=CalibreDBW.get_calibre_version())

# Device Management
@app.route('/devices/list')
def device_list():
    devices = app.database.list_devices()
    url = urljoin(request.host_url, url_for('device_register'))
    return render_template('device_list.html', deviceslist=devices,
            url=url, title='Devices', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/devices/save', methods=['POST'])
def device_save():
    if 'device_id' in request.form and \
            'device_name' in request.form and \
            'device_formats' in request.form:
        uid = request.form.get('device_id')
        name = request.form.get('device_name')
        formats = request.form.get('device_formats')
        book_tags_filters = request.form.get('book_tags_filters', '')
        device = app.database.get_device(uid=uid)
        if not device:
            app.database.add_device(uid=uid, name=name, formats=formats, book_tags_filters=book_tags_filters)
        else:
            app.database.update_device(uid=uid, name=name, formats=formats, book_tags_filters=book_tags_filters)
        flash_success('Device %s saved!' % name)
    else:
        flash_error('Couldn\'t save device')
    return redirect(url_for("device_list"))

@app.route('/devices/edit/<device_id>')
def device_edit(device_id):
    device = app.database.get_device(uid=device_id)
    if not device:
        device = app.database.generate_device(device_id)
    return render_template('activate_device.html', device=device,
            title='Activate Device', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/devices/delete/<device_id>')
def device_delete(device_id):
    device = app.database.get_device(uid=device_id)
    if device:
        app.database.delete_device(device_id)
        flash_success('Device deleted!')
    else:
        flash_error('Device not found')
    return redirect(url_for("device_list"))

# Book feed for reading devices
@app.route('/feeds/')
def device_register():
    uid = app.database.get_new_uid()
    activate_url = '%sdevices/edit/%s' % (request.host_url, uid)
    return render_template('register_device.html', activate_url=activate_url,
            device_id=uid, title='New Device', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/feeds/<device_id>')
@app.route('/feeds/<device_id>/<int:page>')
def device_feed(device_id, page=1):
    device = app.database.get_device(device_id)
    if not device:
        return redirect(url_for("device_register"))
    book_format = device.formats.upper()
    books = app.calibredb_wrap.books_by_format_and_tags(book_format, tags=device.book_tags_filters, page=page)
    return render_template('feed.html', books=books, title=device.name,
            book_format=book_format, page=page, device_id=device_id, calibre_version=CalibreDBW.get_calibre_version())

@app.route('/feeds/<device_id>/books/<int:book_id>/file/<book_format>/')
def device_feed_download_book_file(device_id, book_id, book_format):
    device = app.database.get_device(device_id)
    if not device:
        return redirect(url_for("device_register"))
    return download_book_file(book_id, book_format)

@app.route('/feeds/<device_id>/books/<int:book_id>/cover')
def device_feed_get_cover(device_id, book_id):
    device = app.database.get_device(device_id)
    if not device:
        return redirect(url_for("device_register"))
    return get_cover(book_id)

# List views
@app.route('/tasks')
def list_tasks():
    tasks = app.calibredb_wrap.list_tasks()
    return render_template('tasklist.html', tasklist=tasks,
            title='Tasks list', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/authors')
def list_authors():
    authors = app.calibredb_wrap.list_authors()
    return render_template('list.html', itemlist=authors,
            title='Authors list', scope='authors', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/tags')
def list_tags():
    tags = app.calibredb_wrap.list_tags()
    return render_template('list.html', itemlist=tags,
            title='Tags list', scope='tags', calibre_version=CalibreDBW.get_calibre_version())

@app.route('/series')
def list_series():
    series = app.calibredb_wrap.list_series()
    return render_template('list.html', itemlist=series,
            title='Series list', scope='series', calibre_version=CalibreDBW.get_calibre_version())

# Books
@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
def book_edit(book_id):
    book, formats = app.calibredb_wrap.get_book_details(book_id)
    if not book:
        return redirect(url_for("index"))
    book_formats = {'formats_sizes': formats,
            'formats_list': [i['format'] for i in formats]}
    return render_template('book_detail.html',
            book=book,
            formats=book_formats,
            formats_to=app.config['CALIBRE_EXT_CONV'],
            preferred=app.config['FORMAT_PREFERRED'],
            calibre_version=CalibreDBW.get_calibre_version())

@app.route('/books/<int:book_id>/metadata', methods=['POST'])
def book_refresh_metadata(book_id):
    return { 'success': app.calibredb_wrap.fetch_metadata(book_id, app.config['CALIBRE_TEMP_DIR'])}

@app.route('/books/<int:book_id>/save', methods=['POST'])
def book_save(book_id):
    metadata = {}
    book, formats = app.calibredb_wrap.get_book_details(book_id)
    for field in ['title', 'authors', 'publisher', 'comments', 'tags',
            'languages', 'pubdate', 'series', 'series_index']:
        if field in request.form and \
                request.form.get(field) != book[field]:
            metadata[field] = request.form.get(field)

    if 'rating' in request.form and \
            request.form.get('rating') != book['rating']:
        if request.form.get('rating') == 'Not rated':
            metadata['rating'] = -1
        else:
            metadata['rating'] = int(request.form.get('rating')) * 2
    if 'pubdate' in metadata:
        metadata['pubdate'] = '%s+00:00' % 'T'.join(metadata['pubdate'].split(' '))

    if len(metadata) == 0:
        flash_error('No changes saved')
    elif app.calibredb_wrap.save_metadata(book_id, metadata) == 0:
        flash_success('Metadata updated!')
    else:
        flash_error('Error updating metadata')
    return redirect(url_for("book_edit", book_id=book_id))

@app.route('/books/<int:book_id>/formats/<book_format>/delete')
def delete_book_format(book_id, book_format):
    if app.calibredb_wrap.remove_format(book_id, book_format) == 0:
        flash_success('%s deleted!' % book_format)
    else:
        flash_error('Could not delete %s' % book_format)
    return redirect(url_for("book_edit", book_id=book_id))

@app.route('/books/<int:book_id>/delete')
def delete_book(book_id):
    if app.calibredb_wrap.remove_book(book_id) == 0:
        flash_success('Book #%i deleted successfully!' % book_id)
    else:
        flash_error('Could not delete book #%i' % book_id)
    return redirect(url_for("index"))

@app.route('/books/<int:book_id>/formats/add', methods=['POST'])
def add_format(book_id):
    if 'format_upload' in request.files:
        for format_file in request.files.getlist('format_upload'):
            ext = format_file.filename.split('.')
            if len(ext) <= 1 or ext[-1].upper() not in app.config['CALIBRE_EXT_UP']:
                flash_error('Could not add %s to library (Invalid file)' % format_file.filename)
                return redirect(url_for("index"))
            tmp_dir = app.config['CALIBRE_TEMP_DIR']
            tmp_file = os.path.join(tmp_dir,  secure_filename(format_file.filename))
            format_file.save(tmp_file)
            if app.calibredb_wrap.add_format(book_id, tmp_file) == 0:
                flash_success('%s uploaded and added to library' % format_file.filename)
            else:
                flash_error('Could not add %s to library' % format_file.filename)
            os.remove(tmp_file)
        return redirect(url_for("book_edit", book_id=book_id))
    else:
        flash_error('Please select a file to upload')
        return redirect(url_for("book_edit", book_id=book_id))

@app.route('/books/upload', methods=['POST'])
def upload():
    if 'books_upload' in request.files:
        for book_file in request.files.getlist('books_upload'):
            ext = book_file.filename.split('.')
            if len(ext) <= 1 or ext[-1].upper() not in app.config['CALIBRE_EXT_UP']:
                flash_error('Could not add %s to library (Invalid file)' % book_file.filename)
                return redirect(url_for("index"))
            tmp_dir = app.config['CALIBRE_TEMP_DIR']
            tmp_file = os.path.join(tmp_dir,  secure_filename(book_file.filename))
            book_file.save(tmp_file)
            rc, book_id = app.calibredb_wrap.add_book(tmp_file)
            if rc == 0:
                flash_success('%s uploaded and added to library' % book_file.filename)
                if ext[-1].upper() in app.config['AUTOCONVERT']:
                   app.calibredb_wrap.convert_book(book_id,
                                                   ext[-1].upper(),
                                                   app.config['AUTOCONVERT'][ext[-1].upper()])
            else:
                flash_error('Could not add %s to library' % book_file.filename)
            os.remove(tmp_file)
        return redirect(url_for("index"))
    else:
        flash_error('Please select a file to upload')
        return redirect(url_for("index"))

@app.route('/books/<int:book_id>/convert', methods=['POST'])
def convert_book(book_id):
    if 'format_from' in request.form and 'format_to' in request.form:
        app.calibredb_wrap.convert_book(book_id, request.form['format_from'], request.form['format_to'])
        flash_success('Conversion started for book id %i from %s to %s' % (book_id, request.form['format_from'], request.form['format_to']))
        return redirect(url_for("list_tasks"))
    return redirect(url_for('index'))

@app.route('/books/<int:book_id>/cover')
def get_cover(book_id):
    book = app.calibredb_wrap.get_book(book_id)
    if book and book.has_cover:
        return send_from_directory(os.path.join(
            app.config['CALIBRE_LIBRARY_PATH'], book.path),
            'cover.jpg')
    return redirect('/static/img/default_cover.jpg')

@app.route('/books/<int:book_id>/file/<book_format>/')
def download_book_file(book_id, book_format):
    fpath, fname = app.calibredb_wrap.get_book_file(book_id,
            book_format.upper())
    return send_from_directory(fpath, fname, conditional=True, download_name=fname, as_attachment=True)


