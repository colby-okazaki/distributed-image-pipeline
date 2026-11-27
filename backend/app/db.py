from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    # Test each connection before handing it out, so a Postgres restart costs a
    # reconnect instead of failing the next request with a dead connection.
    check=ConnectionPool.check_connection,
    open=False,
)
