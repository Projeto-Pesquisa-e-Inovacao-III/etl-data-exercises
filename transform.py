from dataclasses import dataclass

import pandas as pd


@dataclass
class PreparedData:
    body_parts: pd.DataFrame
    equipment: pd.DataFrame
    secondary_muscles: pd.DataFrame
    exercises: pd.DataFrame
    exercise_secondary_muscles: pd.DataFrame


def summarize_instructions(row: pd.Series, instruction_cols: list[str]) -> str:
    steps = []
    step_num = 1
    for column in instruction_cols:
        value = row[column]
        if pd.notna(value) and str(value).strip():
            steps.append(f"{step_num}. {str(value).strip()}")
            step_num += 1
    return "\n".join(steps)


def prepare_data(df: pd.DataFrame) -> PreparedData:
    """Consolida instruções e prepara os DataFrames relacionais do ETL."""
    instruction_cols = [
        column for column in df.columns if column.startswith("instructions/")
    ]
    prepared_df = df.copy()
    prepared_df["instructions_sumarization"] = prepared_df.apply(
        summarize_instructions,
        axis=1,
        instruction_cols=instruction_cols,
    )

    secondary_cols = [
        column for column in prepared_df.columns
        if column.startswith("secondaryMuscles/")
    ]
    raw_muscles = []
    for column in secondary_cols:
        raw_muscles.extend(prepared_df[column].dropna().unique().tolist())

    secondary_muscles = sorted({
        str(muscle).strip()
        for muscle in raw_muscles
        if pd.notna(muscle)
        and str(muscle).lower() != "nan"
        and str(muscle).strip()
    })

    body_parts = pd.DataFrame({
        "name": sorted(prepared_df["bodyPart"].dropna().unique())
    })
    equipment = pd.DataFrame({
        "name": sorted(prepared_df["equipment"].dropna().unique())
    })
    secondary_muscle_table = pd.DataFrame({"name": secondary_muscles})

    exercises = pd.DataFrame({
        "name": prepared_df["name"],
        "gif_url": prepared_df["gif_url"],
        "instructions_sumarization": prepared_df["instructions_sumarization"],
        "body_part_name": prepared_df["bodyPart"],
        "equipment_name": prepared_df["equipment"],
    })

    relations = []
    for _, row in prepared_df.iterrows():
        for column in secondary_cols:
            muscle = row[column]
            if pd.notna(muscle) and str(muscle).strip():
                relations.append({
                    "exercise_name": row["name"],
                    "exercise_gif_url": row["gif_url"],
                    "secondary_muscle_name": str(muscle).strip(),
                })

    exercise_secondary_muscles = pd.DataFrame(
        relations,
        columns=[
            "exercise_name",
            "exercise_gif_url",
            "secondary_muscle_name",
        ],
    ).drop_duplicates()

    return PreparedData(
        body_parts=body_parts,
        equipment=equipment,
        secondary_muscles=secondary_muscle_table,
        exercises=exercises,
        exercise_secondary_muscles=exercise_secondary_muscles,
    )
