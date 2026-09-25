from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Base


def make_engine(db_path):
    return create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )


def init_db(settings: Settings) -> sessionmaker[Session]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
