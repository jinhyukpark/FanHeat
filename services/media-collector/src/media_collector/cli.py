import argparse
import json

from .config import get_settings
from .db import SessionLocal
from .models import Base
from .db import engine
from .schemas import CollectionRequest
from .service import CollectionService, ConnectorRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="FANHEAT media collector")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Create tables for local development only")
    collect = subparsers.add_parser("collect", help="Run one collection synchronously")
    collect.add_argument("source", choices=["youtube", "x", "news"])
    collect.add_argument("query")
    collect.add_argument("--max-results", type=int, default=25)
    args = parser.parse_args()

    if args.command == "init-db":
        Base.metadata.create_all(engine)
        return
    with SessionLocal() as db:
        result = CollectionService(db, ConnectorRegistry(get_settings())).run(
            CollectionRequest(source=args.source, query=args.query, max_results=args.max_results)
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
