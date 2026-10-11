from pathlib import Path

import pandas as pd


def read_exercises_csv(filename: str | Path) -> pd.DataFrame:
    """Lê a base de exercícios sem aplicar transformações."""
    data = pd.read_csv(filename)
    return data.rename(columns={"gifUrl": "gif_url"})
