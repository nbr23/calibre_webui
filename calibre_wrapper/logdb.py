from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
from queue import Queue
from threading import Thread
import os

Base = declarative_base()

class JobLogs(Base):
    __tablename__ = 'joblogs'
    id = Column(Integer, primary_key=True)
    message = Column(String)
    status = Column(String)

    def __repr__(self):
        return '[%i] %s - %s' % (self.id, self.status, self.message)

class Actions:
    CLEAR = 0
    INSERT = 1
    UPDATE = 2

class JobLogsDB:
    def create_db(self):
        Base.metadata.create_all(self._db_ng)

    def __init__(self, config):
        db_path = os.path.join(config['CALIBRE_WEBUI_DB_PATH'],
                'calibrewebui_joblogs.db')
        self._db_ng = create_engine('sqlite:///%s' % db_path)
        if not os.path.isfile(db_path):
            self.create_db()
        self._session_maker = sessionmaker(bind=self._db_ng)

    def clear_joblogs(self):
        session = self._session_maker()
        results = session.query(JobLogs).all()
        for result in results:
            session.delete(result)
        session.commit()
        session.close()

    def list_joblogs(self):
        session = self._session_maker()
        results = session.query(JobLogs).all()
        session.close()
        return [{'message': i.message, 'status': i.status} for i in results]

    def push_joblog(self, message, status):
        session = self._session_maker()
        joblog = JobLogs(message=message, status=status)
        session.add(joblog)
        session.commit()
        jobid = joblog.id
        session.close()
        return jobid

    def update_joblog(self, id, message, status):
        session = self._session_maker()
        joblog = session.query(JobLogs).filter(JobLogs.id == id).first()
        joblog.message = message
        joblog.status = status
        session.commit()
        session.close()
