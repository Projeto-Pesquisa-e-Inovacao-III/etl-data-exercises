from pathlib import Path

import pandas as pd


def read_exercises_csv(filename: str | Path) -> pd.DataFrame:
    """Lê a base de exercícios sem aplicar transformações."""
    return pd.read_csv(filename)
