import os
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text


def create_database_engine(connection_string: str | None = None) -> Engine:
    connection_string = connection_string or os.getenv("MYSQL_URL")
    if not connection_string:
        raise RuntimeError(
            "Defina a variável de ambiente MYSQL_URL antes de acessar o banco. "
            "Exemplo: mysql+pymysql://usuario:senha@localhost:3306/spring_api_system"
        )
    return create_engine(connection_string)


def run_sql(
    engine: Engine,
    query: str,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    return pd.read_sql_query(text(query), con=engine, params=params or {})
