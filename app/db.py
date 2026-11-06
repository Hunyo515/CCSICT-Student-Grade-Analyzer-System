"""
Thin wrapper around python-oracledb.

We use python-oracledb in "thin" mode (pure Python, no Oracle Instant Client
required) with a session pool created once at app start-up. Every request
borrows a connection from the pool and returns it automatically.
"""
import oracledb
<<<<<<< HEAD
import re
from flask import current_app, g, has_request_context
=======
from flask import current_app, g
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423

_pool = None


def init_pool(app):
    """Create the Oracle session pool once, at application start-up."""
    global _pool
<<<<<<< HEAD
    schema = app.config.get("ORACLE_SCHEMA", "")
    if schema and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,29}", schema):
        raise RuntimeError("ORACLE_SCHEMA must be a simple Oracle schema identifier.")
    def initialize_connection(connection, requested_tag):
        connection.call_timeout = 15000
        if schema:
            connection.current_schema = schema.upper()
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    _pool = oracledb.create_pool(
        user=app.config["ORACLE_USER"],
        password=app.config["ORACLE_PASSWORD"],
        dsn=app.config["ORACLE_DSN"],
        min=app.config["ORACLE_POOL_MIN"],
        max=app.config["ORACLE_POOL_MAX"],
        increment=app.config["ORACLE_POOL_INCREMENT"],
<<<<<<< HEAD
        getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
        wait_timeout=5000,
        session_callback=initialize_connection,
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    )
    app.logger.info("Oracle connection pool created for dsn=%s", app.config["ORACLE_DSN"])


def get_connection():
    """Return a request-scoped connection, borrowed from the pool."""
    if "db_conn" not in g:
        g.db_conn = _pool.acquire()
<<<<<<< HEAD
        g.db_conn.call_timeout = 15000
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    return g.db_conn


def close_connection(exception=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
<<<<<<< HEAD
        try:
            conn.rollback()
        finally:
            _pool.release(conn)
=======
        _pool.release(conn)
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


def register_teardown(app):
    app.teardown_appcontext(close_connection)

<<<<<<< HEAD
    @app.after_request
    def finish_transaction(response):
        conn = g.get("db_conn")
        if conn is not None:
            try:
                if response.status_code < 400:
                    conn.commit()
                else:
                    conn.rollback()
            except oracledb.DatabaseError:
                from flask import make_response
                # Commit acknowledgement can be ambiguous: never claim success or
                # automatically retry a write whose result must be checked.
                response = make_response("Database confirmation failed. Reload and verify the record before retrying.", 503)
                response.headers["Cache-Control"] = "no-store"
        return response

=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423

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
<<<<<<< HEAD
        if commit and not has_request_context():
=======
        if commit:
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
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
<<<<<<< HEAD
        if not has_request_context():
            conn.commit()
=======
        conn.commit()
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
        return int(out_var.getvalue()[0])
    finally:
        cursor.close()
