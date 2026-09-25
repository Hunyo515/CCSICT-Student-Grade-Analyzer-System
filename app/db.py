"""
Thin wrapper around python-oracledb.

We use python-oracledb in "thin" mode (pure Python, no Oracle Instant Client
required) with a session pool created once at app start-up. Every request
borrows a connection from the pool and returns it automatically.
"""
import oracledb
from flask import current_app, g

_pool = None


def init_pool(app):
    """Create the Oracle session pool once, at application start-up."""
    global _pool
    _pool = oracledb.create_pool(
        user=app.config["ORACLE_USER"],
        password=app.config["ORACLE_PASSWORD"],
        dsn=app.config["ORACLE_DSN"],
        min=app.config["ORACLE_POOL_MIN"],
        max=app.config["ORACLE_POOL_MAX"],
        increment=app.config["ORACLE_POOL_INCREMENT"],
    )
    app.logger.info("Oracle connection pool created for dsn=%s", app.config["ORACLE_DSN"])


def get_connection():
    """Return a request-scoped connection, borrowed from the pool."""
    if "db_conn" not in g:
        g.db_conn = _pool.acquire()
    return g.db_conn


def close_connection(exception=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        _pool.release(conn)


def register_teardown(app):
    app.teardown_appcontext(close_connection)


# ---------------------------------------------------------------------------
# Query helpers: return dict rows instead of raw tuples/cursor objects.
# ---------------------------------------------------------------------------

def _cursor():
    conn = get_connection()
    cursor = conn.cursor()
    return conn, cursor


def _rows_to_dicts(cursor, rows):
    columns = [col[0].lower() for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def query_all(sql, params=None):
    """Run a SELECT and return a list of dict rows."""
    conn, cursor = _cursor()
    try:
        cursor.execute(sql, params or {})
        rows = cursor.fetchall()
        return _rows_to_dicts(cursor, rows)
    finally:
        cursor.close()


def query_one(sql, params=None):
    """Run a SELECT expected to return 0 or 1 row."""
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None, commit=True):
    """Run an INSERT/UPDATE/DELETE. Returns the cursor for RETURNING clauses."""
    conn, cursor = _cursor()
    try:
        cursor.execute(sql, params or {})
        if commit:
            conn.commit()
        return cursor
    finally:
        cursor.close()


def execute_returning_id(sql, params, id_var_name="out_id"):
    """
    Helper for INSERT ... RETURNING id INTO :out_id patterns.
    `sql` must contain `RETURNING <pk_col> INTO :out_id`.
    """
    conn, cursor = _cursor()
    try:
        out_var = cursor.var(oracledb.NUMBER)
        params = dict(params)
        params[id_var_name] = out_var
        cursor.execute(sql, params)
        conn.commit()
        return int(out_var.getvalue()[0])
    finally:
        cursor.close()
