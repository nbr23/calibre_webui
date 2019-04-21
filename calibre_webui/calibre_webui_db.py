import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
import uuid

Base = declarative_base()

class Device(Base):
    __tablename__ = 'devices'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    uid = Column(String, unique=True)
    formats = Column(String)

class CalibreWebUIDB:
    def create_db(self):
        Base.metadata.create_all(self._db_ng)

    def __init__(self, config):
        db_path = os.path.join(config['CALIBRE_WEBUI_DB_PATH'],
                'calibrewebui.db')
        self._db_ng = create_engine('sqlite:///%s' % db_path)
        if not os.path.isfile(db_path):
            self.create_db()
        self._session_maker = sessionmaker(bind=self._db_ng)

    def get_new_uid(self):
        uid = uuid.uuid4().hex
        session = self._session_maker()
        results = session.query(Device).filter(Device.uid == uid).first()
        session.close()
        if not results:
            return uid
        return self.get_new_uuid()

    def generate_device(self, uid):
        return Device(uid=uid, name='', formats='')

    def add_device(self, uid, name, formats):
        session = self._session_maker()
        new_device = Device(name=name, uid=uid, formats=formats)
        session.add(new_device)
        session.commit()
        session.close()

    def update_device(self, uid, name, formats):
        session = self._session_maker()
        device = session.query(Device).filter(Device.uid == uid).first()
        device.name = name
        device.formats = formats
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

