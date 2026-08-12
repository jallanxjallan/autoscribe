from asc.ledger.connect import connect
from asc.ledger.queries import SELECT_CALL_SQL,SELECT_CALLS_SQL,SELECT_RESULT_SQL,SELECT_RESULTS_SQL
from asc.ledger.schema import drop_user_objects,ensure_ledger_schema
from asc.ledger.util import fetch_all_dicts,fetch_one_dict
def init_database(*,force=False):
    with connect() as conn:
        if force: drop_user_objects(conn)
        ensure_ledger_schema(conn)
def read_call(identity):
    with connect() as conn:return fetch_one_dict(conn,SELECT_CALL_SQL,(identity,))
def read_calls():
    with connect() as conn:return fetch_all_dicts(conn,SELECT_CALLS_SQL)
def read_result(identity):
    with connect() as conn:return fetch_one_dict(conn,SELECT_RESULT_SQL,(identity,))
def read_results():
    with connect() as conn:return fetch_all_dicts(conn,SELECT_RESULTS_SQL)
__all__=["init_database","read_call","read_calls","read_result","read_results"]
