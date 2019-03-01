import subprocess
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select, expression
from sqlalchemy.ext.compiler import compiles
from threading import Thread
import os
import uuid

class group_concat(expression.FunctionElement):
    name = "group_concat"

@compiles(group_concat, 'sqlite')
def group_concat_sqlite(element, compiler, **kw):
    compiled = tuple(map(compiler.process, element.clauses))
    if len(compiled) == 2:
        return 'GROUP_CONCAT(%s, %s)' % compiled
    elif len(compiled) == 1:
        return 'GROUP_CONCAT(%s)' % compiled

class CalibreDBW:
    def __init__(self, config, redis_db):
        self._task_list_name = 'CALIBRE_WEBUI_TASKS_LIST'
        self._redis_db = redis_db
        self._config = config
        self._calibre_lib_dir = self._config['CALIBRE_LIBRARY_PATH']
        self._calibre_db = os.path.join(self._calibre_lib_dir, 'metadata.db')
        self._db_ng = create_engine('sqlite:///%s' % self._calibre_db)
        self.clear_tasks()

    def add_book(self, file_path):
        return subprocess.call(['calibredb', 'add', '-d', file_path,
            '--library-path', self._calibre_lib_dir])

    def add_format(self, book_id, file_path):
        return subprocess.call(['calibredb', 'add_format',
            '--library-path', self._calibre_lib_dir, str(book_id), file_path])

    def remove_format(self, book_id, book_format):
        success = subprocess.call(['calibredb', 'remove_format',
            '--library-path', self._calibre_lib_dir, str(book_id),
            book_format])
        if success == 0 and len(self.get_book_formats(book_id)) < 1:
            return self.remove_book(book_id)
        return success

    def remove_book(self, book_id):
        return subprocess.call(['calibredb', 'remove', '--permanent',
            '--library-path', self._calibre_lib_dir, str(book_id)])

    def list_tasks(self):
        tasks_list = self._redis_db.lrange(self._task_list_name, 0, -1)
        return [self._redis_db.hgetall(task) for task in tasks_list]

    def clear_tasks(self):
        self._redis_db.delete(self._task_list_name)


    def tasks_count(self):
        tasks = self.list_tasks()
        return {
            'CANCELED':
                sum(t['status'] == 'CANCELED' for t in tasks),
            'RUNNING':
                sum(t['status'] == 'RUNNING' for t in tasks),
            'COMPLETED':
                sum(t['status'] == 'COMPLETED' for t in tasks),
            }

    def create_redis_task(self, message, status):
        task_id = uuid.uuid4().hex
        task = {
                'status': status,
                'message': message
                }
        self._redis_db.hmset(task_id, task)
        self._redis_db.lpush(self._task_list_name, task_id)
        return task_id

    def update_task_status(self, task_id, status):
        self._redis_db.hmset(task_id, {'status': status})

    def threaded(fn):
        def wrapper(*args, **kwargs):
            thread = Thread(target=fn, args=args, kwargs=kwargs)
            thread.start()
            return thread
        return wrapper

    @threaded
    def convert_book(self, book_id, format_from, format_to):
        task_id = self.create_redis_task('Convert book « %s » from %s to %s'
                %  (self.get_book_title(book_id), format_from, format_to),
                'RUNNING')
        fpath, fname = self.get_book_file(book_id, format_from)
        tmp_dir = self._config['CALIBRE_TEMP_DIR']
        tmp_file = os.path.join(tmp_dir, 'calibre_temp_%s.%s' % (book_id,
            format_to.lower()))
        fullpath = os.path.join(fpath, fname)
        if subprocess.call(['ebook-convert', fullpath, tmp_file]) == 0:
            if self.get_book(book_id) == None:
                self.add_book(tmp_file)
            else:
                self.add_format(book_id, tmp_file)
            os.remove(tmp_file)
            self.update_task_status(task_id, 'COMPLETED')
        else:
            self.update_task_status(task_id, 'CANCELED')

    def search_books_tags(self, search):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            books_tags_link = Table('books_tags_link',
                    meta, autoload=True)
            tags = Table('tags', meta, autoload=True)

            stm = select([books.c.title,
                books.c.id,
                authors.c.name.label('author')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id)\
                        .join(books_tags_link,
                            books_tags_link.c.book == books.c.id)\
                        .join(tags,
                            books_tags_link.c.tag == tags.c.id))\
                        .where(tags.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())
            return con.execute(stm).fetchall()

    def search_books_series(self, search):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            books_series_link = Table('books_series_link',
                    meta, autoload=True)
            series = Table('series', meta, autoload=True)

            stm = select([books.c.title,
                books.c.id,
                authors.c.name.label('author')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id)\
                        .join(books_series_link,
                            books_series_link.c.book == books.c.id)\
                        .join(series,
                            books_series_link.c.series == series.c.id))\
                        .where(series.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())
            return con.execute(stm).fetchall()

    def search_books_authors(self, search):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)

            stm = select([books.c.title,
                books.c.id,
                authors.c.name.label('author')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id))\
                        .where(authors.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())
            return con.execute(stm).fetchall()

    def search_books(self, search, attribute):
        if attribute and attribute in ['authors', 'series', 'tags'] and search:
            if attribute == 'authors':
                return self.search_books_authors(search)
            elif attribute == 'series':
                return self.search_books_series(search)
            elif attribute == 'tags':
                return self.search_books_tags(search)
        else:
            with self._db_ng.connect() as con:
                meta = MetaData(self._db_ng)
                books = Table('books', meta, autoload=True)
                books_authors_link = Table('books_authors_link',
                        meta, autoload=True)
                authors = Table('authors', meta, autoload=True)
                stm = None
                if search:
                    stm = select([books.c.title,
                        books.c.id,
                        authors.c.name.label('author')])\
                            .select_from(books.join(books_authors_link,
                                books_authors_link.c.book == books.c.id)\
                            .join(authors,
                                books_authors_link.c.author == authors.c.id))\
                            .where(books.c.title.ilike('%%%s%%' % search) |
                                    authors.c.name.ilike('%%%s%%' % search))\
                            .order_by(books.c.last_modified.desc())
                else:
                    stm = select([books.c.title,
                        books.c.id,
                        authors.c.name.label('author')])\
                            .select_from(books.join(books_authors_link,
                                books_authors_link.c.book == books.c.id)\
                            .join(authors,
                                books_authors_link.c.author == authors.c.id))\
                            .order_by(books.c.last_modified.desc())
                return con.execute(stm).fetchall()

    def list_tags(self):
        tags_list = []
        meta = MetaData(self._db_ng)
        tags = Table('tags', meta, autoload=True)
        books_tags_link = Table('books_tags_link', meta, autoload=True)

        with self._db_ng.connect() as con:
            stm = select([tags]).order_by(tags.c.name)
            for tag in con.execute(stm).fetchall():
                stm = select([books_tags_link])\
                        .where(books_tags_link.c.tag == tag.id).count()
                tags_list.append({'name': tag.name,
                    'count': con.execute(stm).first()[0]})
        return tags_list

    def list_series(self):
        series_list = []
        meta = MetaData(self._db_ng)
        series = Table('series', meta, autoload=True)
        books_series_link = Table('books_series_link', meta, autoload=True)

        with self._db_ng.connect() as con:
            stm = select([series]).order_by(series.c.name)
            for serie in con.execute(stm).fetchall():
                stm = select([books_series_link])\
                        .where(books_series_link.c.series == serie.id).count()
                series_list.append({'name': serie.name,
                    'count': con.execute(stm).first()[0]})
        return series_list

    def list_authors(self):
        authors_list = []
        meta = MetaData(self._db_ng)
        authors = Table('authors', meta, autoload=True)
        books_authors_link = Table('books_authors_link', meta, autoload=True)

        with self._db_ng.connect() as con:
            stm = select([authors]).order_by(authors.c.name)
            for author in con.execute(stm).fetchall():
                stm = select([books_authors_link])\
                        .where(books_authors_link.c.author == author.id)\
                        .count()
                authors_list.append({'name': author.name,
                    'count': con.execute(stm).first()[0]})
        return authors_list

    def get_book(self, book_id):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('Books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            stm = select([books.c.title, books.c.path,
                books.c.id,
                authors.c.name.label('author')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id))\
                        .where(books.c.id == book_id)
            return con.execute(stm).first()

    def get_book_details(self, book_id):
        book = self.get_book(book_id)
        formats = self.get_book_formats(book_id)
        return (book, formats)

    def get_book_formats(self, book_id):
        formats = []
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            data = Table('Data', meta, autoload=True)
            stm = select([data]).where(data.c.book == book_id)
            for book_format in con.execute(stm).fetchall():
                formats.append({'format': book_format.format,
                    'size': '%.2f' % (
                        book_format.uncompressed_size / (1024*1024))})
            return formats

    def get_book_title(self, book_id):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('Books', meta, autoload=True)
            stm = select([books.c.title]).where(books.c.id == book_id)
            return con.execute(stm).first().title

    def get_book_file(self, book_id, book_format):
        book_path = self.get_book(book_id).path
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            data = Table('Data', meta, autoload=True)
            stm = select([data]).where(data.c.book == book_id)
            for fmt in con.execute(stm).fetchall():
                if fmt.format == book_format:
                    filename = '%s.%s' % (fmt.name, book_format.lower())
                    filepath = os.path.join(self._calibre_lib_dir, book_path)
                    return filepath, filename
