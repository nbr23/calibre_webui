import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
import uuid

Base = declarative_base()

class Device(Base):
    __tablename__ = 'devices'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    uid = Column(String, unique=True)
    formats = Column(String)
    book_tags_filters = Column(String, server_default=text(''))

class CalibreWebUIDB:
    def create_db(self):
        Base.metadata.create_all(self._db_ng)

    def ensure_columns(self):
        session = self._session_maker()
        try:
            session.query(Device).first()
        except Exception as e:
            with self._db_ng.connect() as con:
                print("Ensuring missing columns")
                con.execute(text('ALTER TABLE devices ADD COLUMN book_tags_filters VARCHAR DEFAULT ""'))


    def __init__(self, config):
        db_path = os.path.join(config['CALIBRE_WEBUI_DB_PATH'],
                'calibrewebui.db')
        self._db_ng = create_engine('sqlite:///%s' % db_path)
        if not os.path.isfile(db_path):
            self.create_db()
        self._session_maker = sessionmaker(bind=self._db_ng)
        self.ensure_columns()

    def get_new_uid(self):
        uid = uuid.uuid4().hex
        session = self._session_maker()
        results = session.query(Device).filter(Device.uid == uid).first()
        session.close()
        if not results:
            return uid
        return self.get_new_uuid()

    def generate_device(self, uid):
        return Device(uid=uid, name='', formats='', book_tags_filters='')

    def add_device(self, uid, name, formats, book_tags_filters):
        session = self._session_maker()
        new_device = Device(name=name, uid=uid, formats=formats, book_tags_filters=book_tags_filters)
        session.add(new_device)
        session.commit()
        session.close()

    def update_device(self, uid, name, formats, book_tags_filters):
        session = self._session_maker()
        device = session.query(Device).filter(Device.uid == uid).first()
        device.name = name
        device.formats = formats
        device.book_tags_filters = book_tags_filters
        session.commit()
        session.close()

    def get_device(self, uid):
        session = self._session_maker()
        results = session.query(Device).filter(Device.uid == uid).first()
        session.close()
        return results

    def list_devices(self):
        session = self._session_maker()
        results = session.query(Device).all()
        session.close()
        return results

    def delete_device(self, uid):
        session = self._session_maker()
        results = session.query(Device).filter(Device.uid == uid).first()
        session.delete(results)
        session.commit()
        session.close()

