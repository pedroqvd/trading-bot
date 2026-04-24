"""Create all tables — safe to run repeatedly."""
from app.database import init_db
from app.monitoring.logger import configure_logging, get_logger


def main() -> None:
    configure_logging()
    log = get_logger(__name__)
    init_db()
    log.info("bootstrap.done")


if __name__ == "__main__":
    main()
