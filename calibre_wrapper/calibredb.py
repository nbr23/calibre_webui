import subprocess
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select, expression
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.engine import RowProxy
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
        return subprocess.run(['calibredb', 'add', '-d', file_path,
            '--library-path', self._calibre_lib_dir]).returncode

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

    def save_metadata(self, book_id, metadata):
        command = ['calibredb', 'set_metadata',
                '--library-path', self._calibre_lib_dir]
        for field, value in metadata.items():
            command.append('-f')
            command.append('%s:%s' % (field, value))
        command.append(str(book_id))
        return subprocess.run(command).returncode

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
        if subprocess.run(['ebook-convert', fullpath,
                            tmp_file]).returncode == 0:
            if self.get_book(book_id) == None:
                self.add_book(tmp_file)
            else:
                self.add_format(book_id, tmp_file)
            os.remove(tmp_file)
            self.update_task_status(task_id, 'COMPLETED')
        else:
            self.update_task_status(task_id, 'CANCELED')

    def search_books_tags(self, search, page=1, limit=30):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            books_tags_link = Table('books_tags_link',
                    meta, autoload=True)
            tags = Table('tags', meta, autoload=True)

            stm = select([books.c.title, books.c.has_cover,
                books.c.id,
                authors.c.name.label('authors')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id)\
                        .join(books_tags_link,
                            books_tags_link.c.book == books.c.id)\
                        .join(tags,
                            books_tags_link.c.tag == tags.c.id))\
                        .where(tags.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
            return con.execute(stm).fetchall()

    def search_books_series(self, search, page=1, limit=30):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            books_series_link = Table('books_series_link',
                    meta, autoload=True)
            series = Table('series', meta, autoload=True)

            stm = select([books.c.title, books.c.has_cover,
                books.c.id,
                authors.c.name.label('authors')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id)\
                        .join(books_series_link,
                            books_series_link.c.book == books.c.id)\
                        .join(series,
                            books_series_link.c.series == series.c.id))\
                        .where(series.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
            return con.execute(stm).fetchall()

    def search_books_authors(self, search, page=1, limit=30):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)

            stm = select([books.c.title, books.c.has_cover,
                books.c.id,
                authors.c.name.label('authors')])\
                        .select_from(books.join(books_authors_link,
                            books_authors_link.c.book == books.c.id)\
                        .join(authors,
                            books_authors_link.c.author == authors.c.id))\
                        .where(authors.c.name.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
            return con.execute(stm).fetchall()


    def books_by_format(self, book_format, page=1, limit=30):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('books', meta, autoload=True)
            data = Table('Data', meta, autoload=True)
            stm = select([books.c.title, books.c.has_cover,
                        books.c.id, data.c.format])\
                        .select_from(books.join(data, data.c.book == books.c.id))\
                        .where(data.c.format == book_format.upper())\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
            return con.execute(stm).fetchall()

    def search_books(self, search, attribute, page=1, limit=30):
        if attribute and attribute in ['authors', 'series', 'tags'] and search:
            if attribute == 'authors':
                return self.search_books_authors(search, page, limit)
            elif attribute == 'series':
                return self.search_books_series(search, page, limit)
            elif attribute == 'tags':
                return self.search_books_tags(search, page, limit)
        else:
            with self._db_ng.connect() as con:
                meta = MetaData(self._db_ng)
                books = Table('books', meta, autoload=True)
                books_authors_link = Table('books_authors_link',
                        meta, autoload=True)
                authors = Table('authors', meta, autoload=True)
                stm = None
                author = select([group_concat(authors.c.name, ';')])\
                        .select_from(authors.join(books_authors_link,
                            books_authors_link.c.author == authors.c.id))\
                            .where(books_authors_link.c.book == books.c.id)\
                            .label('authors')
                if search:
                    stm = select([books.c.title, books.c.has_cover,
                        books.c.id, author])\
                        .where(books.c.title.ilike('%%%s%%' % search) |
                                author.ilike('%%%s%%' % search))\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
                else:
                    stm = select([books.c.title, books.c.has_cover,
                        books.c.id,
                        author])\
                        .order_by(books.c.last_modified.desc())\
                        .limit(limit)\
                        .offset((page - 1) * limit)
                return con.execute(stm).fetchall()

    @staticmethod
    def resultproxy_to_dict(result):
        if not result:
            return {}
        if isinstance(result, RowProxy):
            return {field: result[field] for field in result.keys()}
        res = []
        for row in result:
            res.append({field: row[field] for field in row.keys()})
        return res

    def list_books_attributes(self, attr_table, attr_link_column, attr_column):
        attr_list = []
        meta = MetaData(self._db_ng)
        a_table = Table(attr_table, meta, autoload=True)
        books_attr_link = Table('books_%s_link' % attr_table, meta,
                autoload=True)

        with self._db_ng.connect() as con:
            stm = select([a_table]).order_by(getattr(a_table.c, attr_column))
            for attr in con.execute(stm).fetchall():
                stm = select([books_attr_link])\
                        .where(getattr(books_attr_link.c,
                            attr_link_column) == attr.id).count()
                attr_list.append({'name': getattr(attr, attr_column),
                    'count': con.execute(stm).first()[0]})
        return attr_list

    def list_tags(self):
        return self.list_books_attributes('tags', 'tag', 'name')

    def list_series(self):
        return self.list_books_attributes('series', 'series', 'name')

    def list_authors(self):
        return self.list_books_attributes('authors', 'author', 'name')

    def get_book(self, book_id):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books = Table('Books', meta, autoload=True)
            books_authors_link = Table('books_authors_link',
                    meta, autoload=True)
            authors = Table('authors', meta, autoload=True)
            comments = Table('comments', meta, autoload=True)

            author = select([group_concat(authors.c.name, ';')])\
                    .select_from(authors.join(books_authors_link,
                        books_authors_link.c.author == authors.c.id))\
                    .where(books_authors_link.c.book == books.c.id)\
                    .label('authors')
            comment = select([comments.c.text])\
                    .where(comments.c.book == book_id).label('comments')

            stm = select([books.c.title, books.c.path, books.c.pubdate,
                        books.c.id, books.c.has_cover, author, comment])\
                    .where(books.c.id == book_id)
            return con.execute(stm).first()

    def get_book_attributes(self, book_id, attribute_table_name,
                            attribute_column_name,
                            attribute_link_name,
                            first=False):
        with self._db_ng.connect() as con:
            meta = MetaData(self._db_ng)
            books_attributes_link = Table('books_%s_link'
                    % attribute_table_name,
                    meta, autoload=True)
            attributes = Table(attribute_table_name, meta, autoload=True)

            stm = select([getattr(attributes.c, attribute_column_name)])\
                    .select_from( attributes.join(books_attributes_link,
                        getattr(books_attributes_link.c,
                            attribute_link_name) == attributes.c.id))\
                        .where(books_attributes_link.c.book == book_id)
            if first:
                return self.resultproxy_to_dict(con.execute(stm).first())
            return self.resultproxy_to_dict(con.execute(stm).fetchall())

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
            book['tags'] = ', '.join([tag['name'] for tag in self.get_book_tags(book_id)])
            book['publisher'] = ', '.join([pub['name']
                for pub in self.get_book_publishers(book_id)])
            book['languages'] = ', '.join([lang['lang_code']
                for lang in self.get_book_languages(book_id)])
            rating = self.get_book_ratings(book_id).get('rating')
            book['rating'] = int(rating / 2) if rating else rating
            formats = self.get_book_formats(book_id)
            book['authors'] = ' & '.join(book['authors'].split(';'))
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
