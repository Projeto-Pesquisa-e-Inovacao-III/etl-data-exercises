import argparse
from pathlib import Path

from database import create_database_engine
from extract import read_exercises_csv
from load import insert_data_to_mysql
from transform import prepare_data


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "exercises(1).csv"


def run_pipeline(csv_path: str | Path) -> None:
    raw_data = read_exercises_csv(csv_path)
    prepared_data = prepare_data(raw_data)
    engine = create_database_engine()
    try:
        insert_data_to_mysql(engine, prepared_data)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o ETL de exercícios.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=DEFAULT_CSV_PATH,
        type=Path,
    )
    args = parser.parse_args()
    run_pipeline(args.csv_path)


if __name__ == "__main__":
    main()
