from pathlib import Path
from sqlite3 import Connection, connect
from typing import Any, Sequence
from zipfile import ZipFile

from benchmarks.pybench.persistence.common import BenchAccessProto, BenchOperator, BenchRecord

DATABASE_FILE_NAME = "adaptix_bench.db"


class RecordNotFound(Exception):
    def __init__(self, gid: str, name: str, sub_name: str):
        self.gid = gid
        self.name = name
        self.sub_name = sub_name

    def __str__(self):
        return f"""Record not found for {self.name}/{self.sub_name}({self.gid})."""


def database_initialization(database_name: str):
    create_table_ddl_q = """
    CREATE TABLE IF NOT EXISTS bench (
    is_actual BOOLEAN,
    benchmark_name TEXT,
    benchmark_subname TEXT,
    base TEXT,
    local_id TEXT,
    global_id TEXT,
    tags TEXT,
    kwargs TEXT,
    distributions TEXT,
    data TEXT,
    created_at DATETIME
    );
    """
    index_ddl_q = """
    CREATE UNIQUE INDEX IF NOT EXISTS bench_unique ON bench (
     benchmark_name, benchmark_subname, global_id
    ) WHERE is_actual=TRUE;
     """
    with connect(database_name) as con:
        con.execute(create_table_ddl_q)
        con.execute(index_ddl_q)
        con.commit()


class SQLite3BenchOperator(BenchOperator):
    GET_BENCH_DATA_Q = """
    SELECT data, max(created_at)
    FROM bench
    WHERE benchmark_name = ?
        AND benchmark_subname = ?
        AND global_id = ?;
    """
    INSERT_BENCH_DATA_Q = insert_q = """
    INSERT OR REPLACE INTO bench (
    is_actual,
    benchmark_name,
    benchmark_subname,
    base,
    local_id,
    global_id,
    tags,
    kwargs,
    distributions,
    data,
    created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?);
    """

    def __init__(self, accessor: BenchAccessProto, db_name: str):
        self.accessor = accessor
        self.db_name = db_name

    def read_benchmarks_results(self) -> Sequence[str]:
        con = connect(self.db_name)
        content_container = []
        for schema in self.accessor.schemas:
            global_id = self.accessor.get_id(schema)
            content_container.append(self._bench_data(con, global_id,
                                                      self.accessor.meta.benchmark_name,
                                                      self.accessor.meta.benchmark_subname).decode())
        con.close()
        return content_container

    def bench_data(self, schema: Any) -> str | None:
        con = connect(self.db_name)
        result = con.execute(self.GET_BENCH_DATA_Q,
                             (
                                 self.accessor.meta.benchmark_name,
                                 self.accessor.meta.benchmark_subname,
                                 self.accessor.get_id(schema),
                             ))
        data = result.fetchone()
        if not data:
            return None
        return data[0]

    def _bench_data(self, connection: Connection, bench_id, bench_name: str, bench_sub_name: str) -> bytes:
        result = connection.execute(self.GET_BENCH_DATA_Q, (bench_name, bench_sub_name, bench_id))
        data = result.fetchone()
        if not data:
            raise RecordNotFound(bench_id, bench_name, bench_sub_name)
        return data[0]

    def write_bench_data(self, record: BenchRecord) -> None:

        with connect(self.db_name) as conn:
            conn.execute(self.INSERT_BENCH_DATA_Q, (
                record["is_actual"],
                record["benchmark_name"],
                record["benchmark_subname"],
                record["base"],
                record["local_id"],
                record["global_id"],
                record["tags"],
                record["kwargs"],
                record["distributions"],
                record["data"],
                record["created_at"],
            ))
            conn.commit()

    def write_release_files(
        self,
        release_zip: ZipFile,
        files: list[Path],
    ) -> None:
        connection = connect(self.db_name)
        data = []
        for schema in self.accessor.schemas:
            data.append(self._bench_data(connection, self.accessor.get_id(schema),
                                 self.accessor.meta.benchmark_name,
                                 self.accessor.meta.benchmark_subname))
        connection.close()
        for file_path, data in zip(files, data):
            release_zip.writestr(file_path.name, data)


def sqlite_operator_factory(accessor: BenchAccessProto) -> SQLite3BenchOperator:
    return SQLite3BenchOperator(accessor, DATABASE_FILE_NAME)


if __name__ == "__main__":
    database_initialization(DATABASE_FILE_NAME)
