import argparse
import json

from app.data.database import database_status, initialize_database, reset_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintenance Wizard backend management")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init-db", help="Create SQLite schema and seed sample data")
    subcommands.add_parser("reset-db", help="Delete and recreate SQLite database with sample data")
    subcommands.add_parser("db-status", help="Show SQLite schema version and table counts")
    args = parser.parse_args()

    if args.command == "init-db":
        initialize_database(seed=True)
        print(json.dumps(database_status(), indent=2))
    elif args.command == "reset-db":
        reset_database()
        print(json.dumps(database_status(), indent=2))
    elif args.command == "db-status":
        print(json.dumps(database_status(), indent=2))


if __name__ == "__main__":
    main()
