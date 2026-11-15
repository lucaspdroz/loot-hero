from __future__ import annotations

import mysql.connector
from mysql.connector import MySQLConnection
from app.config import settings


def connect(*, with_database: bool = True) -> MySQLConnection:
    params = {
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_user,
        "password": settings.db_password,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if with_database:
        params["database"] = settings.db_name
    return mysql.connector.connect(**params)
