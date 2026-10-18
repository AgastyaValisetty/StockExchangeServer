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
    # Busy timeout prevents immediate lock failures under high concurrent load
    cursor.execute("PRAGMA busy_timeout=5000")
    # 64MB memory page cache for fast lookups
    cursor.execute("PRAGMA cache_size=-64000")
    # Memory-mapped I/O up to 256MB
    cursor.execute("PRAGMA mmap_size=268435456")
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)