from flask import render_template, request, Response, send_from_directory, \
        jsonify, make_response, redirect, url_for, flash
from urllib.parse import urljoin
import os

from calibre_webui import app
from calibre_wrapper.calibredb import CalibreDBW

def flash_error(message):
    return flash(message, app.FLASH['error'])

def flash_warning(message):
    return flash(message, app.FLASH['warning'])

def flash_debug(message):
    return flash(message, app.FLASH['debug'])

def flash_success(message):
    return flash(message, app.FLASH['success'])

@app.endpoint('static')
def static(filename):
    static_url = app.config['STATIC_URL']
    return redirect(urljoin(static_url, filename))

@app.route('/', methods=['GET'])
def index():
    search = request.args.get("search").strip().lower() \
            if 'search' in request.args else None
    scope = request.args.get('search_scope').strip() \
            if 'search_scope' in request.args else None
    return render_template('index.html', search=search,
            scope=scope, title='My Books')

@app.route('/api/books')
def get_books():
    page = int(request.args.get('page')) if 'page' in request.args else 1
    search = request.args.get("search").strip().lower() \
            if 'search' in request.args else None
    scope = request.args.get('search_scope').strip() \
            if 'search_scope' in request.args else None
    books = app.calibredb_wrap.search_books(search.lower() if search else None,
            scope.lower() if scope else None,
            page=page)
    dic = app.calibredb_wrap.resultproxy_to_dict(books)
    return jsonify(dic)

@app.route('/tasks')
def list_tasks():
    tasks = app.calibredb_wrap.list_tasks()
    return render_template('tasklist.html', tasklist=tasks,
            title='Tasks list')

@app.route('/api/tasks')
def get_tasks_list():
    tasks = app.calibredb_wrap.list_tasks()
    return jsonify(tasks)

@app.route('/api/tasks/count')
def get_tasks_count():
    return jsonify(app.calibredb_wrap.tasks_count())

@app.route('/authors')
def list_authors():
    authors = app.calibredb_wrap.list_authors()
    return render_template('list.html', itemlist=authors,
            title='Authors list', scope='authors')

@app.route('/tags')
def list_tags():
    tags = app.calibredb_wrap.list_tags()
    return render_template('list.html', itemlist=tags,
            title='Tags list', scope='tags')

@app.route('/series')
def list_series():
    series = app.calibredb_wrap.list_series()
    return render_template('list.html', itemlist=series,
            title='Series list', scope='series')

@app.route('/cover/<int:book_id>')
def get_cover(book_id):
    book = app.calibredb_wrap.get_book(book_id)
    return send_from_directory(os.path.join(
        app.config['CALIBRE_LIBRARY_PATH'], book.path),
        'cover.jpg')

@app.route('/book/<int:book_id>/edit', methods=['GET', 'POST'])
def book_edit(book_id):
    book, formats, tags, publishers = app.calibredb_wrap.get_book_details(book_id)
    if not book:
        return redirect(url_for("index"))
    book_formats = {'formats_sizes': formats,
            'formats_list': [i['format'] for i in formats]}
    return render_template('book_detail.html',
            book=book,
            formats=book_formats,
            tags=tags,
            formats_to=app.config['CALIBRE_EXT_CONV'],
            preferred=app.config['FORMAT_PREFERRED'])

@app.route('/book/<int:book_id>/file/<book_format>/')
def download_book_file(book_id, book_format):
    fpath, fname = app.calibredb_wrap.get_book_file(book_id,
            book_format.upper())
    return send_from_directory(fpath, fname, conditional=True, attachment_filename=fname, as_attachment=True)

@app.route('/book/<int:book_id>/formats')
def get_book_formats(book_id):
    return jsonify(app.calibredb_wrap.get_book_formats(book_id))

@app.route('/book/<int:book_id>/formats/<book_format>/delete')
def delete_book_format(book_id, book_format):
    if app.calibredb_wrap.remove_format(book_id, book_format) == 0:
        flash_success('%s deleted!' % book_format)
    else:
        flash_error('Could not delete %s' % book_format)
    return redirect(url_for("book_edit", book_id=book_id))

@app.route('/book/<int:book_id>/delete')
def delete_book(book_id):
    if app.calibredb_wrap.remove_book(book_id) == 0:
        flash_success('Book #%i deleted successfully!' % book_id)
    else:
        flash_error('Could not delete book #%i' % book_id)
    return redirect(url_for("index"))

@app.route('/book/<int:book_id>/formats/add', methods=['POST'])
def add_format(book_id):
    if 'format_upload' in request.files:
        for format_file in request.files.getlist('format_upload'):
            ext = format_file.filename.split('.')
            if len(ext) <= 1 or ext[1].upper() not in app.config['CALIBRE_EXT_UP']:
                flash_error('Could not add %s to library' % format_file.filename)
                return redirect(url_for("index"))
            tmp_dir = app.config['CALIBRE_TEMP_DIR']
            tmp_file = os.path.join(tmp_dir, format_file.filename)
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

@app.route('/upload', methods=['POST'])
def upload():
    if 'books_upload' in request.files:
        for book_file in request.files.getlist('books_upload'):
            ext = book_file.filename.split('.')
            if len(ext) <= 1 or ext[1].upper() not in app.config['CALIBRE_EXT_UP']:
                flash_error('Could not add %s to library' % book_file.filename)
                return redirect(url_for("index"))
            tmp_dir = app.config['CALIBRE_TEMP_DIR']
            tmp_file = os.path.join(tmp_dir, book_file.filename)
            book_file.save(tmp_file)
            if app.calibredb_wrap.add_book(tmp_file) == 0:
                flash_success('%s uploaded and added to library' % book_file.filename)
            else:
                flash_error('Could not add %s to library' % book_file.filename)
            os.remove(tmp_file)
        return redirect(url_for("index"))
    else:
        flash_error('Please select a file to upload')
        return redirect(url_for("index"))

@app.route('/book/<int:book_id>/convert', methods=['POST'])
def convert_book(book_id):
    if 'format_from' in request.form and 'format_to' in request.form:
        app.calibredb_wrap.convert_book(book_id, request.form['format_from'], request.form['format_to'])
        flash_success('Conversion started for book id %i from %s to %s' % (book_id, request.form['format_from'], request.form['format_to']))
        return redirect(url_for("list_tasks"))
    return redirect(url_for('index'))
