import subprocess
from sqlalchemy import create_engine, Table, MetaData, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select, expression, or_, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.engine import Row
from threading import Thread
from tempfile import NamedTemporaryFile
import re
import os
import uuid
from . import logdb

RE_ADDED_BOOK_ID = re.compile(r"^Added book ids: ([0-9]+)$")
RE_CALIBRE_VERSION = re.compile(r".*calibre ([0-9.]+).*")

class group_concat(expression.FunctionElement):
    name = "group_concat"


def threaded(fn):
    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper

@compiles(group_concat, 'sqlite')
def group_concat_sqlite(element, compiler, **kw):
    compiled = tuple(map(compiler.process, element.clauses))
    if len(compiled) == 2:
        return 'GROUP_CONCAT(%s, %s)' % compiled
    elif len(compiled) == 1:
        return 'GROUP_CONCAT(%s)' % compiled

class CalibreDBW:
    def __init__(self, config):
        self._task_list_name = 'CALIBRE_WEBUI_TASKS_LIST'
        self._config = config
        self._calibre_lib_dir = self._config['CALIBRE_LIBRARY_PATH']
        self._calibre_db = os.path.join(self._calibre_lib_dir, 'metadata.db')
        self._db_ng = create_engine('sqlite:///%s' % self._calibre_db)
        self._session = sessionmaker(self._db_ng)
        self.clear_tasks()

    def add_book(self, file_path):
        book_id = -1
        res = subprocess.run(['calibredb', 'add', '-d', file_path,
            '--library-path', self._calibre_lib_dir], capture_output=True)
        for line in res.stdout.decode().split('\n'):
            m = re.match(RE_ADDED_BOOK_ID, line)
            if m:
                book_id = m.group(1)
        return res.returncode, book_id

    def add_format(self, book_id, file_path):
        return subprocess.run(['calibredb', 'add_format',
            '--library-path', self._calibre_lib_dir, str(book_id),
            file_path]).returncode

    def remove_format(self, book_id, book_format):
        success = subprocess.run(['calibredb', 'remove_format',
            '--library-path', self._calibre_lib_dir, str(book_id),
            book_format]).returncode
        if success == 0 and len(self.get_book_formats(book_id)) < 1:
            return self.remove_book(book_id)
        return success

    def remove_book(self, book_id):
        return subprocess.run(['calibredb', 'remove', '--permanent',
            '--library-path', self._calibre_lib_dir, str(book_id)]).returncode

    def fetch_metadata(self, book_id, tmp_dir):
        book, formats = self.get_book_details(book_id)
        command = ['fetch-ebook-metadata', '-a', book['authors'], '-t', book['title'], '-o']
        tmp_file = NamedTemporaryFile(dir=tmp_dir)
        ret = subprocess.run(command, stdout=tmp_file)
        if ret.returncode != 0:
            return False
        command = ['calibredb', 'set_metadata', str(book_id), tmp_file.name, '--library-path', self._calibre_lib_dir]
        ret = subprocess.run(command)
        if ret.returncode != 0:
            return False
        return subprocess.run(['calibredb',
                                'embed_metadata',
                                str(book_id)]).returncode == 0


    def save_metadata(self, book_id, metadata):
        command = ['calibredb', 'set_metadata',
                '--library-path', self._calibre_lib_dir]
        for field, value in metadata.items():
            command.append('-f')
            command.append('%s:%s' % (field, value))
        command.append(str(book_id))
        return subprocess.run(command).returncode

    def list_tasks(self):
        return logdb.JobLogsDB(self._config).list_joblogs()

    def clear_tasks(self):
        return logdb.JobLogsDB(self._config).clear_joblogs()

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

    @threaded
    def convert_book(self, book_id, format_from, format_to):
        task_name = 'Convert book « %s » from %s to %s' \
                    % (self.get_book_title(book_id), format_from, format_to)
        task_id = logdb.JobLogsDB(self._config).push_joblog(task_name, 'RUNNING')
        fpath, fname = self.get_book_file(book_id, format_from)
        tmp_dir = self._config['CALIBRE_TEMP_DIR']
        tmp_file = os.path.join(tmp_dir, 'calibre_temp_%s_%i.%s' % (book_id,
            uuid.uuid4().fields[1], format_to.lower()))
        fullpath = os.path.join(fpath, fname)
        if subprocess.run(['ebook-convert', fullpath,
                            tmp_file]).returncode == 0:
            if self.get_book(book_id) == None:
                self.add_book(tmp_file)
            else:
                self.add_format(book_id, tmp_file)
            os.remove(tmp_file)
            logdb.JobLogsDB(self._config).update_joblog(task_id, task_name, 'COMPLETED')
        else:
            logdb.JobLogsDB(self._config).update_joblog(task_id, task_name, 'CANCELED')

    def search_books(self, search, attribute, page=1, limit=20, book_format=None):
        with self._session() as session:
            meta = MetaData()
            books = Table('books', meta, autoload_with=self._db_ng)

            authors_table = Table('authors', meta, autoload_with=self._db_ng)
            books_authors_link = Table('books_authors_link',
                    meta, autoload_with=self._db_ng)
            author = select(group_concat(authors_table.c.name, ';'))\
                    .select_from(authors_table.join(books_authors_link,
                        books_authors_link.c.author == authors_table.c.id))\
                        .where(books_authors_link.c.book == books.c.id)\
                        .label('authors')

            books_series_link = Table('books_series_link',
                    meta, autoload_with=self._db_ng)
            series_table = Table('series', meta, autoload_with=self._db_ng)
            series = select(series_table.c.name)\
                    .select_from(series_table.join(books_series_link,
                        books_series_link.c.series == series_table.c.id))\
                    .where(books_series_link.c.book == books.c.id)\
                    .label('series')

            tags_table = Table('tags', meta, autoload_with=self._db_ng)
            books_tags_link = Table('books_tags_link',
                    meta, autoload_with=self._db_ng)
            tags = select(group_concat(tags_table.c.name, ', '))\
                    .select_from(tags_table.join(books_tags_link,
                        books_tags_link.c.tag == tags_table.c.id))\
                    .where(books_tags_link.c.book == books.c.id)\
                    .label('tags')

            data_table = Table('Data', meta, autoload_with=self._db_ng)
            formats = select(func.group_concat(data_table.c.format, ','))\
                .where(data_table.c.book == books.c.id)\
                .correlate(books)\
                .scalar_subquery()\
                .label('formats')

            query = select(books.c.title, books.c.has_cover,
                books.c.id, author, series, tags, books.c.series_index, formats)
            query = query.select_from(books.join(data_table, data_table.c.book == books.c.id))

            if book_format:
                format_conditions = []
                for f in book_format.split(','):
                    format_conditions.append(func.upper(data_table.c.format) == f.upper())
                query = query.where(or_(*format_conditions))

            query = query.group_by(books.c.id, books.c.title, books.c.has_cover,
                                books.c.series_index, author, series, tags)

            if search:
                if attribute and attribute in ['authors', 'series', 'tags']:
                    match attribute:
                        case 'authors':
                            query = query.where(author.ilike('%%%s%%' % search))
                        case 'series':
                            query = query.where(series.ilike('%%%s%%' % search))
                        case 'tags':
                            query = query.where(
                                or_(*[
                                    tags.contains(search_tag) for search_tag in search.split(',')
                                ])
                            )
                else:
                    query = query.where(books.c.title.ilike('%%%s%%' % search) |
                            author.ilike('%%%s%%' % search))

            if attribute == 'series':
                query = query.order_by(books.c.series_index)
            else :
                query = query.order_by(books.c.last_modified.desc())
            query = query.limit(limit)\
                    .offset((page - 1) * limit)
            result = self.resultproxy_to_dict(session.execute(query).all())
            result = [dict(book, **{'read': len([tag for tag in (book.get('tags') or '').split(',') if tag.strip() == 'read']) > 0})
                    for book in result]
            return result

    @staticmethod
    def resultproxy_to_dict(result):
        if not result:
            return {}
        if isinstance(result, Row):
            return {field: getattr(result, field) for field in result._fields}
        res = []
        for row in result:
            res.append(CalibreDBW.resultproxy_to_dict(row))
        return res

    _CALIBRE_VERSION = None
    @staticmethod
    def get_calibre_version():
        if CalibreDBW._CALIBRE_VERSION:
            return CalibreDBW._CALIBRE_VERSION
        res = subprocess.run(['calibre', '--version'], capture_output=True)
        m = re.match(RE_CALIBRE_VERSION, res.stdout.decode().replace("\n", ""))
        CalibreDBW._CALIBRE_VERSION = m.group(1)
        return CalibreDBW._CALIBRE_VERSION

    def list_books_attributes(self, attr_table, attr_link_column):
        attr_list = []
        meta = MetaData()
        a_table = Table(attr_table, meta, autoload_with=self._db_ng)
        books_attr_link = Table('books_%s_link' % attr_table, meta, autoload_with=self._db_ng)

        with self._session() as session:
            stm = select(a_table).order_by(a_table.c.name)
            for attr in session.execute(stm).fetchall():
                stm = select(books_attr_link)\
                        .where(getattr(books_attr_link.c,
                            attr_link_column) == attr.id)
                attr_list.append({'name': attr.name,
                    'count': len(session.execute(stm).all())})
        return attr_list

    def list_tags(self):
        return self.list_books_attributes('tags', 'tag')

    def list_series(self):
        return self.list_books_attributes('series', 'series')

    def list_authors(self):
        return self.list_books_attributes('authors', 'author')

    def get_book(self, book_id):
        with self._session() as session:
            meta = MetaData()
            books = Table('Books', meta, autoload_with=self._db_ng)
            books_authors_link = Table('books_authors_link',
                    meta, autoload_with=self._db_ng)
            authors = Table('authors', meta, autoload_with=self._db_ng)
            comments = Table('comments', meta, autoload_with=self._db_ng)
            identifiers = Table('identifiers', meta, autoload_with=self._db_ng)
            books_series_link = Table('books_series_link',
                    meta, autoload_with=self._db_ng)
            series = Table('series', meta, autoload_with=self._db_ng)

            author = select(group_concat(authors.c.name, ';'))\
                    .select_from(authors.join(books_authors_link,
                        books_authors_link.c.author == authors.c.id))\
                    .where(books_authors_link.c.book == books.c.id)\
                    .label('authors')
            series = select(series.c.name)\
                    .select_from(series.join(books_series_link,
                        books_series_link.c.series == series.c.id))\
                    .where(books_series_link.c.book == books.c.id)\
                    .label('series')
            comment = select(comments.c.text)\
                    .where(comments.c.book == book_id).label('comments')

            isbn = select(identifiers.c.val)\
                    .where(and_(identifiers.c.book == book_id,
                        identifiers.c.type == 'isbn')).label('isbn')

            stm = select(books.c.title, books.c.path, books.c.pubdate,
                        books.c.has_cover, books.c.id, books.c.series_index,
                        author, comment, isbn, series)\
                    .where(books.c.id == book_id)
            return session.execute(stm).first()

    def get_book_attributes(self, book_id, attribute_table_name,
                            attribute_column_name,
                            attribute_link_name,
                            first=False):
        with self._session() as session:
            meta = MetaData()
            books_attributes_link = Table('books_%s_link'
                    % attribute_table_name,
                    meta, autoload_with=self._db_ng)
            attributes = Table(attribute_table_name, meta, autoload_with=self._db_ng)

            stm = select(getattr(attributes.c, attribute_column_name))\
                    .select_from( attributes.join(books_attributes_link,
                        getattr(books_attributes_link.c,
                            attribute_link_name) == attributes.c.id))\
                        .where(books_attributes_link.c.book == book_id)
            res = session.execute(stm)

            if res is None:
                return {} if first else []
            if first:
                return self.resultproxy_to_dict(res.first())

            return self.resultproxy_to_dict(res.all())

    def get_book_tags(self, book_id):
        return self.get_book_attributes(book_id, 'tags', 'name', 'tag')

    def get_book_publishers(self, book_id):
        return self.get_book_attributes(book_id, 'publishers', 'name',
                'publisher')

    def get_book_ratings(self, book_id):
        return self.get_book_attributes(book_id, 'ratings', 'rating', 'rating',
                first=True)

    def get_book_languages(self, book_id):
        return self.get_book_attributes(book_id, 'languages', 'lang_code',
                'lang_code')

    def get_book_details(self, book_id):
        book, formats = self.resultproxy_to_dict(self.get_book(book_id)), None
        if book:
            tags = self.get_book_tags(book_id)
            book['tags'] = ', '.join([tag['name'] for tag in tags])
            book['publisher'] = ', '.join([pub['name']
                for pub in self.get_book_publishers(book_id)])
            book['languages'] = ', '.join([lang['lang_code']
                for lang in self.get_book_languages(book_id)])
            rating = self.get_book_ratings(book_id).get('rating')
            book['rating'] = int(rating / 2) if rating else rating
            formats = self.get_book_formats(book_id)
            book['authors'] = ' & '.join(book['authors'].split(';'))
            book['series'] = ' & '.join(book['series'].split(';')) if book['series'] else ''
            book['read'] = len([tag['name'] for tag in tags if tag['name'] == 'read']) > 0
        return (book, formats)

    def get_book_formats(self, book_id):
        formats = []
        with self._session() as session:
            meta = MetaData()
            data = Table('Data', meta, autoload_with=self._db_ng)
            stm = select(data).where(data.c.book == book_id)
            for book_format in session.execute(stm).fetchall():
                formats.append({'format': book_format.format,
                    'size': '%.2f' % (
                        book_format.uncompressed_size / (1024*1024))})
            return formats

    def get_book_title(self, book_id):
        with self._session() as session:
            meta = MetaData()
            books = Table('Books', meta, autoload_with=self._db_ng)
            stm = select(books.c.title).where(books.c.id == book_id)
            return session.execute(stm).first().title

    def get_book_file(self, book_id, book_format):
        book_path = self.get_book(book_id).path
        with self._session() as session:
            meta = MetaData()
            data = Table('Data', meta, autoload_with=self._db_ng)
            stm = select(data).where(data.c.book == book_id)
            for fmt in session.execute(stm).fetchall():
                if fmt.format == book_format:
                    filename = '%s.%s' % (fmt.name, book_format.lower())
                    filepath = os.path.join(self._calibre_lib_dir, book_path)
                    return filepath, filename
