import os
import re
import time
import threading
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union


class HellcatDBError(Exception):
    """"""


class HellcatDBConnectionError(HellcatDBError):
    """"""


class HellcatDBQueryError(HellcatDBError):
    """"""


class HellcatDBDriverError(HellcatDBError):
    """"""


class HellcatDBMigrationError(HellcatDBError):
    """"""


class HellcatDBNotFoundError(HellcatDBError):
    """"""


class HellcatDBPoolExhaustedError(HellcatDBError):
    """"""


DriverSqlite   = "sqlite"
DriverPostgres = "postgres"
DriverMysql    = "mysql"
DriverMongo    = "mongo"


def DetectDriver(DB):
    if DB is None:
        raise HellcatDBDriverError("DB parameter is required")

    Lower = DB.lower().strip()

    if Lower.startswith("postgres://") or Lower.startswith("postgresql://"):
        return DriverPostgres
    if Lower.startswith("mysql://") or Lower.startswith("mariadb://"):
        return DriverMysql
    if Lower.startswith("mongodb://") or Lower.startswith("mongodb+srv://"):
        return DriverMongo
    if Lower.endswith(".db") or Lower.endswith(".sqlite") or Lower.endswith(".sqlite3") or Lower.endswith(".sql"):
        return DriverSqlite
    if Lower == ":memory:":
        return DriverSqlite

    raise HellcatDBDriverError(
        f"Cannot detect database driver from '{DB}'. "
        f"Use a file path (*.db, *.sqlite, *.sql) for SQLite, "
        f"or a DSN like postgres://user:pass@host/db, mysql://..., mongodb://..."
    )


class HellcatDBPool:
    """"""

    def __init__(self, Factory, MinConns=1, MaxConns=10, TimeoutSeconds=30):
        self.Factory        = Factory
        self.MinConns       = MinConns
        self.MaxConns       = MaxConns
        self.TimeoutSeconds = TimeoutSeconds
        self.Pool           = []
        self.InUse          = 0
        self.Lock           = threading.Lock()
        self.Available      = threading.Semaphore(MaxConns)
        self.TotalCreated   = 0
        self.TotalErrors    = 0

        for _ in range(MinConns):
            self.Pool.append(self.Factory())
            self.TotalCreated += 1

    def Acquire(self):
        if not self.Available.acquire(timeout=self.TimeoutSeconds):
            raise HellcatDBPoolExhaustedError(
                f"Connection pool exhausted after {self.TimeoutSeconds}s. "
                f"Max connections: {self.MaxConns}"
            )
        with self.Lock:
            if self.Pool:
                Conn = self.Pool.pop()
            else:
                Conn = self.Factory()
                self.TotalCreated += 1
            self.InUse += 1
        return Conn

    def Release(self, Conn):
        with self.Lock:
            self.Pool.append(Conn)
            self.InUse = max(0, self.InUse - 1)
        self.Available.release()

    def Discard(self, Conn):
        try:
            Conn.close()
        except Exception:
            pass
        with self.Lock:
            self.InUse = max(0, self.InUse - 1)
            self.TotalErrors += 1
        self.Available.release()

    def Stats(self):
        with self.Lock:
            return {
                "PoolSize":     len(self.Pool),
                "InUse":        self.InUse,
                "MaxConns":     self.MaxConns,
                "TotalCreated": self.TotalCreated,
                "TotalErrors":  self.TotalErrors,
            }

    def Close(self):
        with self.Lock:
            for Conn in self.Pool:
                try:
                    Conn.close()
                except Exception:
                    pass
            self.Pool.clear()


class HellcatQueryBuilder:
    """"""

    def __init__(self, Adapter, Table):
        self.Adapter    = Adapter
        self.TableName  = Table
        self.Conditions = []
        self.Params     = []
        self.OrderByCols= []
        self.LimitVal   = None
        self.OffsetVal  = None
        self.SelectCols = ["*"]
        self.JoinClauses= []

    def Select(self, *Columns):
        self.SelectCols = list(Columns)
        return self

    def Where(self, Condition, *Params):
        self.Conditions.append(Condition)
        self.Params.extend(Params)
        return self

    def WhereEq(self, Column, Value):
        Ph = self.Adapter.Placeholder()
        self.Conditions.append(f"{Column} = {Ph}")
        self.Params.append(Value)
        return self

    def WhereLike(self, Column, Pattern):
        Ph = self.Adapter.Placeholder()
        self.Conditions.append(f"{Column} LIKE {Ph}")
        self.Params.append(Pattern)
        return self

    def WhereIn(self, Column, Values):
        if not Values:
            self.Conditions.append("1 = 0")
            return self
        Phs = ", ".join(self.Adapter.Placeholder() for _ in Values)
        self.Conditions.append(f"{Column} IN ({Phs})")
        self.Params.extend(Values)
        return self

    def OrderBy(self, Column, Direction="ASC"):
        Dir = "DESC" if Direction.upper() == "DESC" else "ASC"
        self.OrderByCols.append(f"{Column} {Dir}")
        return self

    def Limit(self, N):
        self.LimitVal = int(N)
        return self

    def Offset(self, N):
        self.OffsetVal = int(N)
        return self

    def Join(self, Table, On, JoinType="INNER"):
        self.JoinClauses.append(f"{JoinType} JOIN {Table} ON {On}")
        return self

    def LeftJoin(self, Table, On):
        return self.Join(Table, On, "LEFT")

    def BuildSelect(self):
        Cols  = ", ".join(self.SelectCols)
        Query = f"SELECT {Cols} FROM {self.TableName}"
        if self.JoinClauses:
            Query += " " + " ".join(self.JoinClauses)
        if self.Conditions:
            Query += " WHERE " + " AND ".join(self.Conditions)
        if self.OrderByCols:
            Query += " ORDER BY " + ", ".join(self.OrderByCols)
        if self.LimitVal is not None:
            Query += f" LIMIT {self.LimitVal}"
        if self.OffsetVal is not None:
            Query += f" OFFSET {self.OffsetVal}"
        return Query, self.Params

    def All(self):
        Query, Params = self.BuildSelect()
        return self.Adapter.Query(Query, Params)

    def First(self):
        self.Limit(1)
        Results = self.All()
        return Results[0] if Results else None

    def Count(self):
        Cols        = self.SelectCols
        self.SelectCols = ["COUNT(*) AS Total"]
        Query, Params   = self.BuildSelect()
        self.SelectCols = Cols
        Result = self.Adapter.Query(Query, Params)
        return Result[0]["Total"] if Result else 0

    def Delete(self):
        Query = f"DELETE FROM {self.TableName}"
        if self.Conditions:
            Query += " WHERE " + " AND ".join(self.Conditions)
        return self.Adapter.Execute(Query, self.Params)

    def Update(self, Data):
        if not Data:
            raise HellcatDBQueryError("Update() requires at least one field")
        Ph      = self.Adapter.Placeholder
        Sets    = ", ".join(f"{K} = {Ph()}" for K in Data)
        Vals    = list(Data.values()) + self.Params
        Query   = f"UPDATE {self.TableName} SET {Sets}"
        if self.Conditions:
            Query += " WHERE " + " AND ".join(self.Conditions)
        return self.Adapter.Execute(Query, Vals)

    def Paginate(self, Page=1, PerPage=20):
        Page    = max(1, int(Page))
        PerPage = max(1, int(PerPage))
        Total   = self.Count()
        self.Limit(PerPage).Offset((Page - 1) * PerPage)
        Rows    = self.All()
        return {
            "Data":       Rows,
            "Total":      Total,
            "Page":       Page,
            "PerPage":    PerPage,
            "TotalPages": max(1, -(-Total // PerPage)),
            "HasNext":    Page * PerPage < Total,
            "HasPrev":    Page > 1,
        }


class HellcatSqliteAdapter:
    """"""

    def __init__(self, DSN, PoolSize=5, CheckSameThread=False):
        self.DSN   = DSN
        self.Local = threading.local()

        def Factory():
            Conn = sqlite3.connect(DSN, check_same_thread=CheckSameThread)
            Conn.row_factory = sqlite3.Row
            Conn.execute("PRAGMA journal_mode=WAL")
            Conn.execute("PRAGMA foreign_keys=ON")
            Conn.execute("PRAGMA synchronous=NORMAL")
            return Conn

        self.Pool = HellcatDBPool(Factory, MinConns=1, MaxConns=PoolSize)

    def Placeholder(self):
        return "?"

    @contextmanager
    def Connection(self):
        Conn = self.Pool.Acquire()
        try:
            yield Conn
            Conn.commit()
        except Exception:
            try:
                Conn.rollback()
            except Exception:
                pass
            self.Pool.Discard(Conn)
            raise
        else:
            self.Pool.Release(Conn)

    def Query(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.execute(SQL, Params or [])
                Rows   = Cursor.fetchall()
                return [dict(Row) for Row in Rows]
            except sqlite3.Error as Err:
                raise HellcatDBQueryError(f"Query failed: {Err}\nSQL: {SQL}") from Err

    def QueryOne(self, SQL, Params=None):
        Rows = self.Query(SQL, Params)
        return Rows[0] if Rows else None

    def Execute(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.execute(SQL, Params or [])
                return Cursor.rowcount
            except sqlite3.Error as Err:
                raise HellcatDBQueryError(f"Execute failed: {Err}\nSQL: {SQL}") from Err

    def ExecuteMany(self, SQL, ParamsList):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.executemany(SQL, ParamsList)
                return Cursor.rowcount
            except sqlite3.Error as Err:
                raise HellcatDBQueryError(f"ExecuteMany failed: {Err}\nSQL: {SQL}") from Err

    def Insert(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.execute(SQL, Params or [])
                return Cursor.lastrowid
            except sqlite3.Error as Err:
                raise HellcatDBQueryError(f"Insert failed: {Err}\nSQL: {SQL}") from Err

    def InsertRow(self, Table, Data):
        if not Data:
            raise HellcatDBQueryError("InsertRow() requires at least one field")
        Cols  = ", ".join(Data.keys())
        Phs   = ", ".join("?" for _ in Data)
        SQL   = f"INSERT INTO {Table} ({Cols}) VALUES ({Phs})"
        return self.Insert(SQL, list(Data.values()))

    def UpsertRow(self, Table, Data, ConflictCols):
        if not Data:
            raise HellcatDBQueryError("UpsertRow() requires at least one field")
        Cols      = ", ".join(Data.keys())
        Phs       = ", ".join("?" for _ in Data)
        UpdateSet = ", ".join(
            f"{K} = excluded.{K}"
            for K in Data
            if K not in ConflictCols
        )
        Conflict  = ", ".join(ConflictCols)
        SQL       = (
            f"INSERT INTO {Table} ({Cols}) VALUES ({Phs}) "
            f"ON CONFLICT({Conflict}) DO UPDATE SET {UpdateSet}"
        )
        return self.Insert(SQL, list(Data.values()))

    @contextmanager
    def Transaction(self):
        with self.Connection() as Conn:
            try:
                yield HellcatTransactionContext(Conn, self)
            except Exception:
                raise

    def TableExists(self, TableName):
        Result = self.QueryOne(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [TableName]
        )
        return Result is not None

    def Tables(self):
        Rows = self.Query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [R["name"] for R in Rows]

    def Schema(self, TableName):
        Rows = self.Query(f"PRAGMA table_info({TableName})")
        return Rows

    def Stats(self):
        return self.Pool.Stats()

    def Close(self):
        self.Pool.Close()

    def Table(self, TableName):
        return HellcatQueryBuilder(self, TableName)


class HellcatPostgresAdapter:
    """"""

    def __init__(self, DSN, PoolSize=10):
        try:
            import psycopg2
            import psycopg2.extras
            self.psycopg2 = psycopg2
            self.extras   = psycopg2.extras
        except ImportError:
            raise HellcatDBDriverError(
                "psycopg2 is not installed. Run: pip install psycopg2-binary"
            )

        self.DSN = DSN

        def Factory():
            Conn = psycopg2.connect(DSN)
            Conn.autocommit = False
            return Conn

        self.Pool = HellcatDBPool(Factory, MinConns=2, MaxConns=PoolSize)

    def Placeholder(self):
        return "%s"

    @contextmanager
    def Connection(self):
        Conn = self.Pool.Acquire()
        try:
            yield Conn
            Conn.commit()
        except Exception:
            try:
                Conn.rollback()
            except Exception:
                pass
            self.Pool.Discard(Conn)
            raise
        else:
            self.Pool.Release(Conn)

    def Query(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.cursor(cursor_factory=self.extras.RealDictCursor)
                Cursor.execute(SQL, Params or [])
                return [dict(Row) for Row in Cursor.fetchall()]
            except self.psycopg2.Error as Err:
                raise HellcatDBQueryError(f"Query failed: {Err}\nSQL: {SQL}") from Err

    def QueryOne(self, SQL, Params=None):
        Rows = self.Query(SQL, Params)
        return Rows[0] if Rows else None

    def Execute(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.cursor()
                Cursor.execute(SQL, Params or [])
                return Cursor.rowcount
            except self.psycopg2.Error as Err:
                raise HellcatDBQueryError(f"Execute failed: {Err}\nSQL: {SQL}") from Err

    def ExecuteMany(self, SQL, ParamsList):
        with self.Connection() as Conn:
            try:
                Cursor = Conn.cursor()
                Cursor.executemany(SQL, ParamsList)
                return Cursor.rowcount
            except self.psycopg2.Error as Err:
                raise HellcatDBQueryError(f"ExecuteMany failed: {Err}\nSQL: {SQL}") from Err

    def Insert(self, SQL, Params=None):
        ReturningSQL = SQL.rstrip().rstrip(";") + " RETURNING id"
        with self.Connection() as Conn:
            try:
                Cursor = Conn.cursor()
                Cursor.execute(ReturningSQL, Params or [])
                Row = Cursor.fetchone()
                return Row[0] if Row else None
            except self.psycopg2.Error as Err:
                raise HellcatDBQueryError(f"Insert failed: {Err}\nSQL: {SQL}") from Err

    def InsertRow(self, Table, Data):
        if not Data:
            raise HellcatDBQueryError("InsertRow() requires at least one field")
        Cols = ", ".join(Data.keys())
        Phs  = ", ".join("%s" for _ in Data)
        SQL  = f"INSERT INTO {Table} ({Cols}) VALUES ({Phs})"
        return self.Insert(SQL, list(Data.values()))

    def UpsertRow(self, Table, Data, ConflictCols):
        if not Data:
            raise HellcatDBQueryError("UpsertRow() requires at least one field")
        Cols      = ", ".join(Data.keys())
        Phs       = ", ".join("%s" for _ in Data)
        UpdateSet = ", ".join(
            f"{K} = EXCLUDED.{K}"
            for K in Data
            if K not in ConflictCols
        )
        Conflict  = ", ".join(ConflictCols)
        SQL       = (
            f"INSERT INTO {Table} ({Cols}) VALUES ({Phs}) "
            f"ON CONFLICT ({Conflict}) DO UPDATE SET {UpdateSet}"
        )
        return self.Insert(SQL, list(Data.values()))

    @contextmanager
    def Transaction(self):
        with self.Connection() as Conn:
            yield HellcatTransactionContext(Conn, self)

    def TableExists(self, TableName):
        Result = self.QueryOne(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename=%s",
            [TableName]
        )
        return Result is not None

    def Tables(self):
        Rows = self.Query(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        return [R["tablename"] for R in Rows]

    def Schema(self, TableName):
        return self.Query(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",
            [TableName]
        )

    def Stats(self):
        return self.Pool.Stats()

    def Close(self):
        self.Pool.Close()

    def Table(self, TableName):
        return HellcatQueryBuilder(self, TableName)


class HellcatMysqlAdapter:
    """"""

    def __init__(self, DSN, PoolSize=10):
        try:
            import pymysql
            import pymysql.cursors
            self.pymysql = pymysql
        except ImportError:
            raise HellcatDBDriverError(
                "pymysql is not installed. Run: pip install pymysql"
            )

        self.DSN  = DSN
        self.Args = self.ParseDSN(DSN)

        def Factory():
            Conn = pymysql.connect(
                **self.Args,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
            return Conn

        self.Pool = HellcatDBPool(Factory, MinConns=2, MaxConns=PoolSize)

    def ParseDSN(self, DSN):
        Match = re.match(
            r"(?:mysql|mariadb)://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([^?]+)",
            DSN
        )
        if not Match:
            raise HellcatDBConnectionError(
                f"Invalid MySQL DSN format. Expected: mysql://user:pass@host:port/dbname"
            )
        return {
            "user":     Match.group(1),
            "password": Match.group(2),
            "host":     Match.group(3),
            "port":     int(Match.group(4) or 3306),
            "database": Match.group(5),
            "charset":  "utf8mb4",
        }

    def Placeholder(self):
        return "%s"

    @contextmanager
    def Connection(self):
        Conn = self.Pool.Acquire()
        try:
            Conn.ping(reconnect=True)
            yield Conn
            Conn.commit()
        except Exception:
            try:
                Conn.rollback()
            except Exception:
                pass
            self.Pool.Discard(Conn)
            raise
        else:
            self.Pool.Release(Conn)

    def Query(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                with Conn.cursor() as Cursor:
                    Cursor.execute(SQL, Params or [])
                    return list(Cursor.fetchall())
            except self.pymysql.Error as Err:
                raise HellcatDBQueryError(f"Query failed: {Err}\nSQL: {SQL}") from Err

    def QueryOne(self, SQL, Params=None):
        Rows = self.Query(SQL, Params)
        return Rows[0] if Rows else None

    def Execute(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                with Conn.cursor() as Cursor:
                    Cursor.execute(SQL, Params or [])
                    return Cursor.rowcount
            except self.pymysql.Error as Err:
                raise HellcatDBQueryError(f"Execute failed: {Err}\nSQL: {SQL}") from Err

    def ExecuteMany(self, SQL, ParamsList):
        with self.Connection() as Conn:
            try:
                with Conn.cursor() as Cursor:
                    Cursor.executemany(SQL, ParamsList)
                    return Cursor.rowcount
            except self.pymysql.Error as Err:
                raise HellcatDBQueryError(f"ExecuteMany failed: {Err}\nSQL: {SQL}") from Err

    def Insert(self, SQL, Params=None):
        with self.Connection() as Conn:
            try:
                with Conn.cursor() as Cursor:
                    Cursor.execute(SQL, Params or [])
                    return Cursor.lastrowid
            except self.pymysql.Error as Err:
                raise HellcatDBQueryError(f"Insert failed: {Err}\nSQL: {SQL}") from Err

    def InsertRow(self, Table, Data):
        if not Data:
            raise HellcatDBQueryError("InsertRow() requires at least one field")
        Cols = ", ".join(Data.keys())
        Phs  = ", ".join("%s" for _ in Data)
        SQL  = f"INSERT INTO {Table} ({Cols}) VALUES ({Phs})"
        return self.Insert(SQL, list(Data.values()))

    def UpsertRow(self, Table, Data, ConflictCols=None):
        if not Data:
            raise HellcatDBQueryError("UpsertRow() requires at least one field")
        Cols      = ", ".join(Data.keys())
        Phs       = ", ".join("%s" for _ in Data)
        UpdateSet = ", ".join(f"{K} = VALUES({K})" for K in Data)
        SQL       = (
            f"INSERT INTO {Table} ({Cols}) VALUES ({Phs}) "
            f"ON DUPLICATE KEY UPDATE {UpdateSet}"
        )
        return self.Insert(SQL, list(Data.values()))

    @contextmanager
    def Transaction(self):
        with self.Connection() as Conn:
            yield HellcatTransactionContext(Conn, self)

    def TableExists(self, TableName):
        Result = self.QueryOne(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            [TableName]
        )
        return Result is not None

    def Tables(self):
        Rows = self.Query(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"
        )
        return [R["TABLE_NAME"] for R in Rows]

    def Schema(self, TableName):
        return self.Query(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT "
            "FROM information_schema.COLUMNS WHERE TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
            [TableName]
        )

    def Stats(self):
        return self.Pool.Stats()

    def Close(self):
        self.Pool.Close()

    def Table(self, TableName):
        return HellcatQueryBuilder(self, TableName)


class HellcatMongoAdapter:
    """"""

    def __init__(self, DSN, DBName=None, PoolSize=10):
        try:
            import pymongo
            self.pymongo = pymongo
        except ImportError:
            raise HellcatDBDriverError(
                "pymongo is not installed. Run: pip install pymongo"
            )

        self.Client = pymongo.MongoClient(DSN, maxPoolSize=PoolSize)
        self.DBName = DBName or self.ParseDBName(DSN)
        self.DB     = self.Client[self.DBName]

    def ParseDBName(self, DSN):
        Match = re.search(r"/([^/?]+)(\?|$)", DSN)
        if Match:
            return Match.group(1)
        raise HellcatDBConnectionError(
            "Cannot detect database name from MongoDB DSN. "
            "Use mongodb://host/dbname or pass DBName= explicitly."
        )

    def Collection(self, Name):
        return HellcatMongoCollection(self.DB[Name])

    def Table(self, Name):
        return self.Collection(Name)

    def Query(self, Collection, Filter=None, Projection=None):
        Col  = self.DB[Collection]
        Rows = Col.find(Filter or {}, Projection or {})
        return [self.Serialize(Doc) for Doc in Rows]

    def QueryOne(self, Collection, Filter=None):
        Col = self.DB[Collection]
        Doc = Col.find_one(Filter or {})
        return self.Serialize(Doc) if Doc else None

    def InsertRow(self, Collection, Data):
        Col    = self.DB[Collection]
        Result = Col.insert_one(Data)
        return str(Result.inserted_id)

    def InsertMany(self, Collection, DataList):
        Col    = self.DB[Collection]
        Result = Col.insert_many(DataList)
        return [str(Id) for Id in Result.inserted_ids]

    def Execute(self, Collection, Filter, Update):
        Col    = self.DB[Collection]
        Result = Col.update_many(Filter, {"$set": Update})
        return Result.modified_count

    def UpsertRow(self, Collection, Filter, Data):
        Col    = self.DB[Collection]
        Result = Col.update_one(Filter, {"$set": Data}, upsert=True)
        return str(Result.upserted_id) if Result.upserted_id else None

    def Serialize(self, Doc):
        if Doc is None:
            return None
        Result = {}
        for K, V in Doc.items():
            if K == "_id":
                Result["_id"] = str(V)
            else:
                Result[K] = V
        return Result

    def Tables(self):
        return self.DB.list_collection_names()

    def TableExists(self, Name):
        return Name in self.DB.list_collection_names()

    def Stats(self):
        return {
            "Driver":   "mongo",
            "Database": self.DBName,
            "Collections": len(self.DB.list_collection_names()),
        }

    def Close(self):
        self.Client.close()


class HellcatMongoCollection:
    """"""

    def __init__(self, Col):
        self.Col        = Col
        self.FilterDict = {}
        self.SortList   = []
        self.LimitVal   = None
        self.SkipVal    = None
        self.ProjDict   = None

    def Where(self, Filter):
        self.FilterDict.update(Filter)
        return self

    def WhereEq(self, Field, Value):
        self.FilterDict[Field] = Value
        return self

    def Select(self, *Fields):
        self.ProjDict = {F: 1 for F in Fields}
        return self

    def OrderBy(self, Field, Direction="ASC"):
        import pymongo
        Dir = pymongo.ASCENDING if Direction.upper() == "ASC" else pymongo.DESCENDING
        self.SortList.append((Field, Dir))
        return self

    def Limit(self, N):
        self.LimitVal = int(N)
        return self

    def Offset(self, N):
        self.SkipVal = int(N)
        return self

    def Serialize(self, Doc):
        if Doc is None:
            return None
        Result = {}
        for K, V in Doc.items():
            Result["_id" if K == "_id" else K] = str(V) if K == "_id" else V
        return Result

    def All(self):
        Cursor = self.Col.find(self.FilterDict, self.ProjDict or {})
        if self.SortList:
            Cursor = Cursor.sort(self.SortList)
        if self.SkipVal:
            Cursor = Cursor.skip(self.SkipVal)
        if self.LimitVal:
            Cursor = Cursor.limit(self.LimitVal)
        return [self.Serialize(D) for D in Cursor]

    def First(self):
        Doc = self.Col.find_one(self.FilterDict, self.ProjDict or {})
        return self.Serialize(Doc)

    def Count(self):
        return self.Col.count_documents(self.FilterDict)

    def Delete(self):
        Result = self.Col.delete_many(self.FilterDict)
        return Result.deleted_count

    def Update(self, Data):
        Result = self.Col.update_many(self.FilterDict, {"$set": Data})
        return Result.modified_count

    def Paginate(self, Page=1, PerPage=20):
        Page    = max(1, int(Page))
        PerPage = max(1, int(PerPage))
        Total   = self.Count()
        self.Limit(PerPage).Offset((Page - 1) * PerPage)
        Rows    = self.All()
        return {
            "Data":       Rows,
            "Total":      Total,
            "Page":       Page,
            "PerPage":    PerPage,
            "TotalPages": max(1, -(-Total // PerPage)),
            "HasNext":    Page * PerPage < Total,
            "HasPrev":    Page > 1,
        }


class HellcatTransactionContext:
    """"""

    def __init__(self, Conn, Adapter):
        self.Conn    = Conn
        self.Adapter = Adapter

    def Query(self, SQL, Params=None):
        try:
            if hasattr(self.Conn, "cursor"):
                Cursor = self.Conn.cursor()
                Cursor.execute(SQL, Params or [])
                Rows = Cursor.fetchall()
                if isinstance(Rows[0] if Rows else None, sqlite3.Row):
                    return [dict(R) for R in Rows]
                return list(Rows) if Rows else []
            return []
        except Exception as Err:
            raise HellcatDBQueryError(f"Transaction query failed: {Err}") from Err

    def Execute(self, SQL, Params=None):
        try:
            Cursor = self.Conn.execute(SQL, Params or [])
            return Cursor.rowcount
        except Exception as Err:
            raise HellcatDBQueryError(f"Transaction execute failed: {Err}") from Err

    def Insert(self, SQL, Params=None):
        try:
            Cursor = self.Conn.execute(SQL, Params or [])
            return Cursor.lastrowid
        except Exception as Err:
            raise HellcatDBQueryError(f"Transaction insert failed: {Err}") from Err


class HellcatMigrationRunner:
    """"""

    MigrationTable = "_hellcat_migrations"

    def __init__(self, Adapter):
        self.Adapter = Adapter
        self.EnsureMigrationTable()

    def EnsureMigrationTable(self):
        if not self.Adapter.TableExists(self.MigrationTable):
            self.Adapter.Execute(
                f"CREATE TABLE {self.MigrationTable} ("
                f"  Id        INTEGER PRIMARY KEY AUTOINCREMENT,"
                f"  Name      TEXT NOT NULL UNIQUE,"
                f"  AppliedAt TEXT NOT NULL"
                f")"
            )

    def Applied(self):
        Rows = self.Adapter.Query(
            f"SELECT Name FROM {self.MigrationTable} ORDER BY Id"
        )
        return {R["Name"] for R in Rows}

    def Run(self, Migrations):
        Applied = self.Applied()
        Ran     = []
        Skipped = []

        for Name, SQL in Migrations.items():
            if Name in Applied:
                Skipped.append(Name)
                continue
            try:
                Statements = [S.strip() for S in SQL.strip().split(";") if S.strip()]
                for Statement in Statements:
                    self.Adapter.Execute(Statement)
                self.Adapter.InsertRow(self.MigrationTable, {
                    "Name":      Name,
                    "AppliedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                Ran.append(Name)
            except Exception as Err:
                raise HellcatDBMigrationError(
                    f"Migration '{Name}' failed: {Err}"
                ) from Err

        return {"Ran": Ran, "Skipped": Skipped}

    def Status(self):
        Rows = self.Adapter.Query(
            f"SELECT Name, AppliedAt FROM {self.MigrationTable} ORDER BY Id"
        )
        return Rows


class HellcatDB:
    """"""

    def __init__(
        self,
        DB,
        PoolSize    = 10,
        DBName      = None,
        AutoMigrate = None,
    ):
        self.DSN      = DB
        self.Driver   = DetectDriver(DB)
        self.Adapter  = self.CreateAdapter(DB, PoolSize, DBName)
        self.Migrations = HellcatMigrationRunner(self.Adapter) if self.Driver != DriverMongo else None

        if AutoMigrate:
            self.Migrate(AutoMigrate)

    def CreateAdapter(self, DB, PoolSize, DBName):
        if self.Driver == DriverSqlite:
            return HellcatSqliteAdapter(DB, PoolSize=PoolSize)
        if self.Driver == DriverPostgres:
            return HellcatPostgresAdapter(DB, PoolSize=PoolSize)
        if self.Driver == DriverMysql:
            return HellcatMysqlAdapter(DB, PoolSize=PoolSize)
        if self.Driver == DriverMongo:
            return HellcatMongoAdapter(DB, DBName=DBName, PoolSize=PoolSize)
        raise HellcatDBDriverError(f"Unsupported driver: {self.Driver}")

    def Table(self, Name):
        return self.Adapter.Table(Name)

    def Query(self, SQL, Params=None):
        return self.Adapter.Query(SQL, Params)

    def QueryOne(self, SQL, Params=None):
        return self.Adapter.QueryOne(SQL, Params)

    def Execute(self, SQL, Params=None):
        return self.Adapter.Execute(SQL, Params)

    def ExecuteMany(self, SQL, ParamsList):
        return self.Adapter.ExecuteMany(SQL, ParamsList)

    def Insert(self, SQL, Params=None):
        return self.Adapter.Insert(SQL, Params)

    def InsertRow(self, Table, Data):
        return self.Adapter.InsertRow(Table, Data)

    def UpsertRow(self, Table, Data, ConflictCols):
        return self.Adapter.UpsertRow(Table, Data, ConflictCols)

    def Transaction(self):
        return self.Adapter.Transaction()

    def TableExists(self, Name):
        return self.Adapter.TableExists(Name)

    def Tables(self):
        return self.Adapter.Tables()

    def Schema(self, Name):
        return self.Adapter.Schema(Name)

    def Migrate(self, Migrations):
        if self.Migrations is None:
            raise HellcatDBMigrationError("Migrations are not supported for MongoDB")
        return self.Migrations.Run(Migrations)

    def MigrationStatus(self):
        if self.Migrations is None:
            raise HellcatDBMigrationError("Migrations are not supported for MongoDB")
        return self.Migrations.Status()

    def Stats(self):
        return {
            "Driver":  self.Driver,
            "DSN":     self.DSN if self.Driver == DriverMongo else self.DSN,
            "Pool":    self.Adapter.Stats(),
        }

    def Close(self):
        self.Adapter.Close()

    def __repr__(self):
        Stats = self.Adapter.Stats()
        return f"<HellcatDB driver={self.Driver} pool={Stats}>"

    async def AsyncQuery(self, SQL, Params=None):
        return self.Query(SQL, Params)

    async def AsyncQueryOne(self, SQL, Params=None):
        return self.QueryOne(SQL, Params)

    async def AsyncExecute(self, SQL, Params=None):
        return self.Execute(SQL, Params)

    async def AsyncInsertRow(self, Table, Data):
        return self.InsertRow(Table, Data)
