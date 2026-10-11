from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from database import run_sql
from transform import PreparedData


ETL_SUMMARY_LOG = Path("etl_summary.log")
ETL_ERROR_LOG = Path("etl_errors.log")


def _write_log(path: Path, message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def _insert_dimension(
    connection: Any,
    table_name: str,
    source_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    existing = pd.read_sql_query(
        text(f"SELECT id, name FROM {table_name}"),
        connection,
    )
    existing_names = set(existing["name"])
    missing = source_frame.loc[
        ~source_frame["name"].isin(existing_names),
        ["name"],
    ]

    if not missing.empty:
        connection.execute(
            text(f"INSERT INTO {table_name} (name) VALUES (:name)"),
            missing.to_dict("records"),
        )

    current = pd.read_sql_query(
        text(f"SELECT id, name FROM {table_name}"),
        connection,
    )
    return current, len(missing)


def insert_data_to_mysql(
    engine: Engine,
    prepared: PreparedData,
) -> None:
    """Insere o ETL com IDs gerados pelo banco e registra a execução."""
    summary = []

    try:
        with engine.begin() as connection:
            body_parts, body_inserted = _insert_dimension(
                connection, "body_part", prepared.body_parts
            )
            summary.append(("body_part", body_inserted, len(prepared.body_parts)))

            equipment, equipment_inserted = _insert_dimension(
                connection, "equipment", prepared.equipment
            )
            summary.append(("equipment", equipment_inserted, len(prepared.equipment)))

            muscles, muscle_inserted = _insert_dimension(
                connection,
                "secondary_muscle",
                prepared.secondary_muscles,
            )
            summary.append((
                "secondary_muscle",
                muscle_inserted,
                len(prepared.secondary_muscles),
            ))

            body_map = dict(zip(body_parts["name"], body_parts["id"]))
            equipment_map = dict(zip(equipment["name"], equipment["id"]))
            muscle_map = dict(zip(muscles["name"], muscles["id"]))

            exercises = prepared.exercises.copy()
            exercises["fk_body_part"] = exercises["body_part_name"].map(body_map)
            exercises["fk_equipment"] = exercises["equipment_name"].map(
                equipment_map
            )
            if exercises[["fk_body_part", "fk_equipment"]].isna().any().any():
                raise ValueError(
                    "Há FKs de exercício sem correspondência nas tabelas de referência."
                )

            existing_exercises = pd.read_sql_query(
                text("SELECT id, name, gifUrl FROM exercise"),
                connection,
            )
            existing_keys = set(zip(
                existing_exercises["name"],
                existing_exercises["gifUrl"],
            ))
            new_exercises = exercises.loc[
                ~exercises.set_index(["name", "gifUrl"]).index.isin(existing_keys),
                [
                    "name",
                    "gifUrl",
                    "instructions_sumarization",
                    "fk_body_part",
                    "fk_equipment",
                ],
            ]

            if not new_exercises.empty:
                connection.execute(
                    text("""
                        INSERT INTO exercise
                            (name, gifUrl, instructions_sumarization,
                             fk_body_part, fk_equipment)
                        VALUES
                            (:name, :gifUrl, :instructions_sumarization,
                             :fk_body_part, :fk_equipment)
                    """),
                    new_exercises.to_dict("records"),
                )

            all_exercises = pd.read_sql_query(
                text("SELECT id, name, gifUrl FROM exercise"),
                connection,
            )
            exercise_map = dict(zip(
                zip(all_exercises["name"], all_exercises["gifUrl"]),
                all_exercises["id"],
            ))
            summary.append(("exercise", len(new_exercises), len(exercises)))

            relations = prepared.exercise_secondary_muscles.copy()
            relations["exercise_id"] = [
                exercise_map.get((name, gif_url))
                for name, gif_url in zip(
                    relations["exercise_name"],
                    relations["exercise_gif_url"],
                )
            ]
            relations["secondary_muscle_id"] = relations[
                "secondary_muscle_name"
            ].map(muscle_map)
            if relations[["exercise_id", "secondary_muscle_id"]].isna().any().any():
                raise ValueError(
                    "Há relações N-N sem exercício ou músculo correspondente."
                )

            relations = relations[
                ["exercise_id", "secondary_muscle_id"]
            ].drop_duplicates()
            existing_relations = pd.read_sql_query(
                text(
                    "SELECT exercise_id, secondary_muscle_id "
                    "FROM exercise_secondary_muscle"
                ),
                connection,
            )
            existing_pairs = set(map(tuple, existing_relations.to_numpy()))
            new_relations = [
                row
                for row in relations.to_dict("records")
                if (row["exercise_id"], row["secondary_muscle_id"])
                not in existing_pairs
            ]

            if new_relations:
                connection.execute(
                    text("""
                        INSERT INTO exercise_secondary_muscle
                            (exercise_id, secondary_muscle_id)
                        VALUES (:exercise_id, :secondary_muscle_id)
                    """),
                    new_relations,
                )
            summary.append((
                "exercise_secondary_muscle",
                len(new_relations),
                len(relations),
            ))

        _write_log(
            ETL_SUMMARY_LOG,
            "SUCESSO | " + " | ".join(
                f"{table}: {inserted}/{total} novas linhas"
                for table, inserted, total in summary
            ),
        )
        print("[Sucesso] ETL concluído. Resumo salvo em etl_summary.log.")
    except Exception as error:
        _write_log(
            ETL_ERROR_LOG,
            f"ERRO | transação revertida | linhas efetivamente inseridas: 0 | {error!r}",
        )
        _write_log(
            ETL_ERROR_LOG,
            "Detalhes | " + " | ".join(
                f"{table}: {inserted}/{total} linhas preparadas"
                for table, inserted, total in summary
            ),
        )
        print("[Erro] ETL revertido pela transação. Detalhes salvos em etl_errors.log.")
        raise


def query_by_body_part(engine: Engine, body_part: str) -> pd.DataFrame:
    query = """
    SELECT e.id, e.name, e.gifUrl, e.instructions_sumarization,
           bp.name AS body_part, eq.name AS equipment
    FROM exercise AS e
    JOIN body_part AS bp ON bp.id = e.fk_body_part
    LEFT JOIN equipment AS eq ON eq.id = e.fk_equipment
    WHERE bp.name = :body_part
    ORDER BY e.name;
    """
    return run_sql(engine, query, {"body_part": body_part})


def query_by_secondary_muscles(
    engine: Engine,
    secondary_muscles: list[str],
) -> pd.DataFrame:
    if not secondary_muscles:
        raise ValueError("Informe pelo menos um músculo secundário.")
    placeholders = ", ".join(
        f":muscle_{index}" for index in range(len(secondary_muscles))
    )
    params = {
        f"muscle_{index}": muscle
        for index, muscle in enumerate(secondary_muscles)
    }
    query = f"""
    SELECT e.id, e.name, e.gifUrl, bp.name AS body_part,
           eq.name AS equipment, COUNT(DISTINCT sm.name) AS matched_muscles
    FROM exercise AS e
    JOIN exercise_secondary_muscle AS esm ON esm.exercise_id = e.id
    JOIN secondary_muscle AS sm ON sm.id = esm.secondary_muscle_id
    LEFT JOIN body_part AS bp ON bp.id = e.fk_body_part
    LEFT JOIN equipment AS eq ON eq.id = e.fk_equipment
    WHERE sm.name IN ({placeholders})
    GROUP BY e.id, e.name, e.gifUrl, bp.name, eq.name
    HAVING COUNT(DISTINCT sm.name) = {len(secondary_muscles)}
    ORDER BY e.name;
    """
    return run_sql(engine, query, params)


def query_by_equipment(
    engine: Engine,
    selected_equipment: list[str],
) -> pd.DataFrame:
    placeholders = ", ".join(
        f":equipment_{index}" for index in range(len(selected_equipment))
    )
    params = {
        f"equipment_{index}": equipment
        for index, equipment in enumerate(selected_equipment)
    }
    query = f"""
    SELECT e.id, e.name, e.gifUrl, bp.name AS body_part,
           eq.name AS equipment
    FROM exercise AS e
    JOIN equipment AS eq ON eq.id = e.fk_equipment
    LEFT JOIN body_part AS bp ON bp.id = e.fk_body_part
    WHERE eq.name IN ({placeholders})
    ORDER BY eq.name, e.name;
    """
    return run_sql(engine, query, params)


def query_bodyweight(engine: Engine) -> pd.DataFrame:
    return run_sql(engine, """
    SELECT e.id, e.name, e.gifUrl, bp.name AS body_part,
           eq.name AS equipment
    FROM exercise AS e
    JOIN equipment AS eq ON eq.id = e.fk_equipment
    LEFT JOIN body_part AS bp ON bp.id = e.fk_body_part
    WHERE eq.name = 'body weight'
    ORDER BY bp.name, e.name;
    """)


def query_equipment_classification(engine: Engine) -> pd.DataFrame:
    return run_sql(engine, """
    SELECT id, name AS equipment,
           CASE
               WHEN name = 'body weight' THEN 'somente o próprio corpo'
               WHEN name = 'assisted' THEN 'assistência externa'
               WHEN name = 'weighted' THEN 'carga externa'
               ELSE 'equipamento externo'
           END AS equipment_type
    FROM equipment
    ORDER BY
        CASE
            WHEN name = 'body weight' THEN 1
            WHEN name IN ('assisted', 'weighted') THEN 2
            ELSE 3
        END,
        name;
    """)
