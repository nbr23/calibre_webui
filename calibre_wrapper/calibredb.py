import subprocess
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import select
import os
import tempfile


class CalibreDBW:
    def __init__(self, calibre_lib_dir):
        self._calibre_lib_dir = calibre_lib_dir
        self._calibre_db = os.path.join(self._calibre_lib_dir, 'metadata.db')
        self.db_ng = create_engine('sqlite:///%s' % self._calibre_db)

    def add_book(self, file_path):
        return subprocess.call(['calibredb', 'add', '-d', file_path,
            '--library-path', self._calibre_lib_dir])

    def add_format(self, book_id, file_path):
        return subprocess.call(['calibredb', 'add_format',
            '--library-path', self._calibre_lib_dir, str(book_id), file_path])

    def remove_format(self, book_id, book_format):
        return subprocess.call(['calibredb', 'remove_format',
            '--library-path', self._calibre_lib_dir, str(book_id),
            book_format])

    def remove_book(self, book_id):
        return subprocess.call(['calibredb', 'remove', '--permanent',
            '--library-path', self._calibre_lib_dir, str(book_id)])

    def search_books_tags(self, search):
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
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
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
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
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
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
            with self.db_ng.connect() as con:
                meta = MetaData(self.db_ng)
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
        meta = MetaData(self.db_ng)
        tags = Table('tags', meta, autoload=True)
        books_tags_link = Table('books_tags_link', meta, autoload=True)

        with self.db_ng.connect() as con:
            stm = select([tags]).order_by(tags.c.name)
            for tag in con.execute(stm).fetchall():
                stm = select([books_tags_link])\
                        .where(books_tags_link.c.tag == tag.id).count()
                tags_list.append({'name': tag.name,
                    'count': con.execute(stm).first()[0]})
        return tags_list

    def list_series(self):
        series_list = []
        meta = MetaData(self.db_ng)
        series = Table('series', meta, autoload=True)
        books_series_link = Table('books_series_link', meta, autoload=True)

        with self.db_ng.connect() as con:
            stm = select([series]).order_by(series.c.name)
            for serie in con.execute(stm).fetchall():
                stm = select([books_series_link])\
                        .where(books_series_link.c.series == serie.id).count()
                series_list.append({'name': serie.name,
                    'count': con.execute(stm).first()[0]})
        return series_list

    def list_authors(self):
        authors_list = []
        meta = MetaData(self.db_ng)
        authors = Table('authors', meta, autoload=True)
        books_authors_link = Table('books_authors_link', meta, autoload=True)

        with self.db_ng.connect() as con:
            stm = select([authors]).order_by(authors.c.name)
            for author in con.execute(stm).fetchall():
                stm = select([books_authors_link])\
                        .where(books_authors_link.c.author == author.id)\
                        .count()
                authors_list.append({'name': author.name,
                    'count': con.execute(stm).first()[0]})
        return authors_list

    def get_book(self, book_id):
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
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
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
            data = Table('Data', meta, autoload=True)
            stm = select([data]).where(data.c.book == book_id)
            for book_format in con.execute(stm).fetchall():
                formats.append({'format': book_format.format,
                    'size': '%.2f' % (
                        book_format.uncompressed_size / (1024*1024))})
            return formats

    def get_book_file(self, book_id, book_format):
        book_path = self.get_book(book_id).path
        with self.db_ng.connect() as con:
            meta = MetaData(self.db_ng)
            data = Table('Data', meta, autoload=True)
            stm = select([data]).where(data.c.book == book_id)
            for fmt in con.execute(stm).fetchall():
                if fmt.format == book_format:
                    filename = '%s.%s' % (fmt.name, book_format.lower())
                    filepath = os.path.join(self._calibre_lib_dir, book_path)
                    return filepath, filename
