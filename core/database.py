from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

sqlite_file_name = "users.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=False, connect_args=connect_args)

def create_db_and_tables() -> None:
    """Create all database tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    """Yield a database session for dependency injection.
    
    Yields:
        Session: A SQLModel database session.
    """
    with Session(engine) as session:
        yield session
