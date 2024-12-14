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
    def _init_tables_metadata(self):
        meta = MetaData()
        self._tables = {
            'books': Table('Books', meta, autoload_with=self._db_ng),
            'authors': Table('authors', meta, autoload_with=self._db_ng),
            'comments': Table('comments', meta, autoload_with=self._db_ng),
            'identifiers': Table('identifiers', meta, autoload_with=self._db_ng),
            'books_series_link': Table('books_series_link', meta, autoload_with=self._db_ng),
            'books_publishers_link': Table('books_publishers_link', meta, autoload_with=self._db_ng),
            'books_tags_link': Table('books_tags_link', meta, autoload_with=self._db_ng),
            'books_authors_link': Table('books_authors_link', meta, autoload_with=self._db_ng),
            'books_languages_link': Table('books_languages_link', meta, autoload_with=self._db_ng),
            'books_ratings_link': Table('books_ratings_link', meta, autoload_with=self._db_ng),
            'series': Table('series', meta, autoload_with=self._db_ng),
            'Data': Table('Data', meta, autoload_with=self._db_ng),
            'tags': Table('tags', meta, autoload_with=self._db_ng),
            'publishers': Table('publishers', meta, autoload_with=self._db_ng),
            'languages': Table('languages', meta, autoload_with=self._db_ng),
            'ratings': Table('ratings', meta, autoload_with=self._db_ng),
        }

    def __init__(self, config):
        self._task_list_name = 'CALIBRE_WEBUI_TASKS_LIST'
        self._config = config
        self._calibre_lib_dir = self._config['CALIBRE_LIBRARY_PATH']
        self._calibre_db = os.path.join(self._calibre_lib_dir, 'metadata.db')
        self._db_ng = create_engine('sqlite:///%s' % self._calibre_db)
        self._session = sessionmaker(self._db_ng)
        self._init_tables_metadata()
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
        try:
            subprocess.run(['ebook-convert', fullpath, tmp_file], check=True)
            if self.get_book(book_id) is None:
                self.add_book(tmp_file)
            else:
                self.add_format(book_id, tmp_file)
            os.remove(tmp_file)
            logdb.JobLogsDB(self._config).update_joblog(task_id, task_name, 'COMPLETED')
        except subprocess.CalledProcessError:
            logdb.JobLogsDB(self._config).update_joblog(task_id, task_name, 'CANCELED')

    def search_books(self, search, attribute, page=1, limit=20, book_format=None):
        with self._session() as session:
            formats = select(func.group_concat(self._tables['Data'].c.format, ','))\
                .where(self._tables['Data'].c.book == self._tables['books'].c.id)\
                .correlate(self._tables['books'])\
                .scalar_subquery()\
                .label('formats')

            select_columns = [
                self._tables['books'].c.title,
                self._tables['books'].c.has_cover,
                self._tables['books'].c.id,
                formats
            ]

            if not attribute or attribute == 'authors' or search:
                author = select(group_concat(self._tables['authors'].c.name, ';'))\
                        .select_from(self._tables['authors'].join(self._tables['books_authors_link'],
                            self._tables['books_authors_link'].c.author == self._tables['authors'].c.id))\
                            .where(self._tables['books_authors_link'].c.book == self._tables['books'].c.id)\
                            .label('authors')
                select_columns.append(author)

            if not attribute or attribute == 'series':
                series = select(self._tables['series'].c.name)\
                        .select_from(self._tables['series'].join(self._tables['books_series_link'],
                            self._tables['books_series_link'].c.series == self._tables['series'].c.id))\
                        .where(self._tables['books_series_link'].c.book == self._tables['books'].c.id)\
                        .label('series')
                select_columns.append(series)
                select_columns.append(self._tables['books'].c.series_index)

            tags = select(group_concat(self._tables['tags'].c.name, ', '))\
                    .select_from(self._tables['tags'].join(self._tables['books_tags_link'],
                        self._tables['books_tags_link'].c.tag == self._tables['tags'].c.id))\
                    .where(self._tables['books_tags_link'].c.book == self._tables['books'].c.id)\
                    .label('tags')
            select_columns.append(tags)

            query = select(*select_columns)
            query = query.select_from(self._tables['books'].join(self._tables['Data'], self._tables['Data'].c.book == self._tables['books'].c.id))

            if book_format:
                format_conditions = [func.upper(self._tables['Data'].c.format) == f.upper()
                                for f in book_format.split(',')]
                query = query.where(or_(*format_conditions))

            group_by_columns = [self._tables['books'].c.id, self._tables['books'].c.title, self._tables['books'].c.has_cover]
            if not attribute or attribute == 'authors' or search:
                group_by_columns.append(author)
            if not attribute or attribute == 'series':
                group_by_columns.extend([series, self._tables['books'].c.series_index])
            if not attribute or attribute == 'tags':
                group_by_columns.append(tags)

            query = query.group_by(*group_by_columns)

            if search:
                if attribute and attribute in ['authors', 'series', 'tags']:
                    match attribute:
                        case 'authors':
                            query = query.where(author.ilike(f'%{search}%'))
                        case 'series':
                            query = query.where(series.ilike(f'%{search}%'))
                        case 'tags':
                            search_tags = search.split(',')
                            include_tags = [tag for tag in search_tags if not tag.startswith('-')]
                            exclude_tags = [tag[1:] for tag in search_tags if tag.startswith('-')]

                            conditions = []
                            if include_tags:
                                conditions.append(or_(*[
                                    or_(
                                        tags == tag,
                                        tags.like(f'{tag},%'),
                                        tags.like(f'%, {tag},%'),
                                        tags.like(f'%, {tag}')
                                    )
                                    for tag in include_tags
                                ]))
                            if exclude_tags:
                                conditions.append(and_(*[
                                    or_(
                                        tags.is_(None),
                                        ~or_(
                                            tags == tag,
                                            tags.like(f'{tag},%'),
                                            tags.like(f'%, {tag},%'),
                                            tags.like(f'%, {tag}')
                                        )
                                    )
                                    for tag in exclude_tags
                                ]))

                            if conditions:
                                query = query.where(and_(*conditions))
                else:
                    query = query.where(
                        or_(
                            self._tables['books'].c.title.ilike(f'%{search}%'),
                            author.ilike(f'%{search}%')
                        )
                    )

            if attribute == 'series':
                query = query.order_by(self._tables['books'].c.series_index)
            else:
                query = query.order_by(self._tables['books'].c.last_modified.desc())

            query = query.limit(limit).offset((page - 1) * limit)

            result = self.resultproxy_to_dict(session.execute(query).all())
            result = [dict(book, **{
                'read': len([tag for tag in (book.get('tags') or '').split(',')
                            if tag.strip() == 'read']) > 0
            }) for book in result]
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

    def list_books_attributes(self, attr_table, attr_link_column, limit=0, page=0):
        attr_list = []
        a_table = self._tables[attr_table]
        books_attr_link = self._tables['books_%s_link' % attr_table]

        with self._session() as session:
            offset = (page - 1) * limit
            count_query = select(func.count()).select_from(a_table)

            stm = select(a_table)\
                .order_by(a_table.c.name)

            if limit > 0 and page > 0:
                stm = stm.limit(limit).offset(offset)

            for attr in session.execute(stm).fetchall():
                count_query = select(func.count())\
                    .select_from(books_attr_link)\
                    .where(getattr(books_attr_link.c, attr_link_column) == attr.id)

                book_count = session.execute(count_query).scalar()

                attr_list.append({
                    'name': attr.name,
                    'count': book_count
                })
        return attr_list

    def list_tags(self, limit=0, page=0):
        return self.list_books_attributes('tags', 'tag', limit, page)

    def list_series(self, limit=0, page=0):
        return self.list_books_attributes('series', 'series', limit, page)

    def list_authors(self, limit=0, page=0):
        return self.list_books_attributes('authors', 'author', limit, page)

    def get_book(self, book_id):
        with self._session() as session:
            author = select(group_concat(self._tables['authors'].c.name, ';'))\
                    .select_from(self._tables['authors'].join(self._tables['books_authors_link'],
                        self._tables['books_authors_link'].c.author == self._tables['authors'].c.id))\
                    .where(self._tables['books_authors_link'].c.book == self._tables['books'].c.id)\
                    .label('authors')
            series = select(self._tables['series'].c.name)\
                    .select_from(self._tables['series'].join(self._tables['books_series_link'],
                        self._tables['books_series_link'].c.series == self._tables['series'].c.id))\
                    .where(self._tables['books_series_link'].c.book == self._tables['books'].c.id)\
                    .label('series')
            comment = select(self._tables['comments'].c.text)\
                    .where(self._tables['comments'].c.book == book_id).label('comments')

            isbn = select(self._tables['identifiers'].c.val)\
                    .where(and_(self._tables['identifiers'].c.book == book_id,
                        self._tables['identifiers'].c.type == 'isbn')).label('isbn')

            stm = select(self._tables['books'].c.title, self._tables['books'].c.path, self._tables['books'].c.pubdate,
                        self._tables['books'].c.has_cover, self._tables['books'].c.id, self._tables['books'].c.series_index,
                        author, comment, isbn, series)\
                    .where(self._tables['books'].c.id == book_id)
            return session.execute(stm).first()

    def get_book_attributes(self, book_id, attribute_table_name,
                            attribute_column_name,
                            attribute_link_name,
                            first=False):
        with self._session() as session:
            books_attributes_link = self._tables['books_%s_link'
                    % attribute_table_name]
            attributes = self._tables[attribute_table_name]

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
            stm = select(self._tables['Data']).where(self._tables['Data'].c.book == book_id)
            for book_format in session.execute(stm).fetchall():
                formats.append({'format': book_format.format,
                    'size': '%.2f' % (
                        book_format.uncompressed_size / (1024*1024))})
            return formats

    def get_book_title(self, book_id):
        with self._session() as session:
            stm = select(self._tables['books'].c.title).where(self._tables['books'].c.id == book_id)
            return session.execute(stm).first().title

    def get_book_file(self, book_id, book_format):
        book_path = self.get_book(book_id).path
        with self._session() as session:
            stm = select(self._tables['Data']).where(self._tables['Data'].c.book == book_id)
            for fmt in session.execute(stm).fetchall():
                if fmt.format == book_format:
                    filename = '%s.%s' % (fmt.name, book_format.lower())
                    filepath = os.path.join(self._calibre_lib_dir, book_path)
                    return filepath, filename
