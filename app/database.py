"""SQLAlchemy database configuration for obmon."""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = "sqlite:///./obmon.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def init_db() -> None:
    """Create database tables when they do not already exist."""

    # Importing models registers their tables on Base.metadata.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # create_all does not add columns to an existing SQLite table. Migrate the
    # obligation fields introduced after the initial prototype in place.
    with engine.begin() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("obligations")
        }
        new_columns = {
            "time_constraint_type": "VARCHAR(32)",
            "time_value": "INTEGER",
            "time_unit": "VARCHAR(64)",
        }
        for column_name, column_type in new_columns.items():
            if column_name not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE obligations ADD COLUMN "
                        f"{column_name} {column_type}"
                    )
                )

        if "deadline_type" in columns:
            connection.execute(
                text(
                    """
                    UPDATE obligations
                    SET time_constraint_type = CASE deadline_type
                        WHEN 'relative' THEN 'relative_deadline'
                        WHEN 'fixed' THEN 'fixed_deadline'
                        WHEN 'ambiguous' THEN 'ambiguous'
                        ELSE 'none'
                    END
                    WHERE time_constraint_type IS NULL
                    """
                )
            )

        alert_columns = {
            column["name"]
            for column in inspect(connection).get_columns("alerts")
        }
        for column_name, column_type in {
            "deadline_state": "VARCHAR(32)",
            "days_remaining": "INTEGER",
            "days_overdue": "INTEGER",
        }.items():
            if column_name not in alert_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE alerts ADD COLUMN "
                        f"{column_name} {column_type}"
                    )
                )
            connection.execute(
                text(
                    """
                    UPDATE obligations
                    SET time_value = deadline_value,
                        time_unit = deadline_unit
                    WHERE time_constraint_type = 'relative_deadline'
                      AND time_value IS NULL
                    """
                )
            )


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
