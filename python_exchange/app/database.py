from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./data/exchange.db"

# QueuePool configured to allow high-concurrency requests without blocking on connections
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=100,
    max_overflow=200,
    pool_timeout=30.0,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # WAL mode allows concurrent readers without blocking readers or writers
    cursor.execute("PRAGMA journal_mode=WAL")
    # NORMAL synchronous mode reduces fsync pauses while remaining durable in WAL
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Busy timeout: wait up to 10 seconds under concurrent write contention
    cursor.execute("PRAGMA busy_timeout=10000")
    # 64MB memory page cache for fast lookups
    cursor.execute("PRAGMA cache_size=-64000")
    # Memory-mapped I/O up to 256MB
    cursor.execute("PRAGMA mmap_size=268435456")
    # Defer WAL checkpointing to avoid pausing writers every 1000 pages
    cursor.execute("PRAGMA wal_autocheckpoint=10000")
    # Disable full fsync on checkpoints for faster write cycles
    cursor.execute("PRAGMA checkpoint_fullfsync=0")
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)