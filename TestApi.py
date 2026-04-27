import os
import asyncio
import time
import random

from cores.App.HellcatApp         import HellcatApp
from cores.DB.HellcatDB           import HellcatDB, HellcatDBQueryError
from cores.Router.HellcatRouter   import HellcatRouter
from cores.Context.HellcatContext import RequestContext

App = HellcatApp(
    TemplateDir="templates",
    StaticDir="static",
    StaticUrl="/static",
    SecretKey="hellcat-super-secret-key-2026",
)

DB = HellcatDB(
    DB="hellcat.db",
    PoolSize=10,
    AutoMigrate={
        "001_create_users": """
            CREATE TABLE users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT NOT NULL,
                email     TEXT NOT NULL UNIQUE,
                role      TEXT NOT NULL DEFAULT 'user',
                created   TEXT NOT NULL
            )
        """,
        "002_create_products": """
            CREATE TABLE products (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                price   REAL NOT NULL,
                stock   INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            )
        """,
        "003_create_orders": """
            CREATE TABLE orders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity   INTEGER NOT NULL DEFAULT 1,
                total      REAL NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                created    TEXT NOT NULL,
                FOREIGN KEY(user_id)    REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        """,
        "004_seed_users": """
            INSERT OR IGNORE INTO users (name, email, role, created) VALUES
                ('Tom',     'tom7@hellcat.dev',    'admin', datetime('now')),
                ('Bob',     'bob@hellcat.dev',     'user',  datetime('now')),
                ('Charlie', 'charlie@hellcat.dev', 'user',  datetime('now'))
        """,
        "005_seed_products": """
            INSERT OR IGNORE INTO products (name, price, stock, created) VALUES
                ('HellcatCore',       49.99,  100, datetime('now')),
                ('HellcatPro',        99.99,   50, datetime('now')),
                ('HellcatEnterprise', 299.99,  10, datetime('now'))
        """,
    },
)

App.UseCors(AllowedOrigins=["*"])
App.UseSecurityHeaders()
App.UseRateLimit(MaxRequests=200, WindowSeconds=60)
App.UseBodySizeLimit(MaxBytes=5 * 1024 * 1024)
App.UseGzip(MinSizeBytes=512)

Host     = "0.0.0.0"
Port     = 9926
CertFile = "certs/cert.pem"
KeyFile  = "certs/key.pem"

RequestLog = []


async def LogRequest(Req, Next):
    Start    = time.time()
    Response = await Next(Req)
    Duration = round((time.time() - Start) * 1000, 2)
    RequestLog.append({
        "Method": Req.Method,
        "Path":   Req.Path,
        "Ip":     Req.RemoteIp,
        "Ms":     Duration,
        "Time":   int(time.time()),
    })
    if len(RequestLog) > 100:
        RequestLog.pop(0)
    return Response


def RequireJson(Req, Next):
    if Req.Method in ("POST", "PUT", "PATCH") and not Req.IsJson:
        return App.Error("Content-Type must be application/json", StatusCode=415)
    return Next(Req)


App.UseMiddleware(LogRequest)


@App.ErrorHandler(404)
def NotFound(Req, Error=None):
    return App.Json(
        {"Error": True, "Message": "Route not found", "Path": Req.Path}, StatusCode=404
    )


@App.ErrorHandler(405)
def MethodNotAllowed(Req, Error=None):
    return App.Json(
        {"Error": True, "Message": "Method not allowed", "Method": Req.Method},
        StatusCode=405,
    )


@App.Get("/")
def Index(Req):
    return App.Render(
        "index.html",
        {
            "Title":   "HellcatAPI",
            "Message": "Server Running!",
            "Server":  f"{Host}:{Port}",
            "Version": "1.0.0",
        },
    )


@App.Get("/ping")
def Ping(Req):
    return App.Json({"Pong": True, "Mode": "sync", "Ts": int(time.time())})


@App.Get("/async-ping")
async def AsyncPing(Req):
    await asyncio.sleep(0)
    return App.Json({"Pong": True, "Mode": "async", "Ts": int(time.time())})


@App.Get("/async-data")
async def AsyncData(Req):
    async def FetchUser():
        await asyncio.sleep(0)
        return DB.Table("users").First()

    async def FetchStats():
        await asyncio.sleep(0)
        return {
            "Requests": len(RequestLog),
            "Uptime":   "99.9%",
            "Users":    DB.Table("users").Count(),
            "Products": DB.Table("products").Count(),
            "Orders":   DB.Table("orders").Count(),
        }

    async def FetchSystem():
        await asyncio.sleep(0)
        return {"Python": "3.11", "Mode": "async", "Workers": os.cpu_count(), "DB": DB.Driver}

    User, Stats, System = await App.Gather(FetchUser(), FetchStats(), FetchSystem())
    return App.Json({"User": User, "Stats": Stats, "System": System})


@App.Post("/async-echo")
async def AsyncEcho(Req):
    Body = Req.GetJson()
    if Body is None:
        return App.Error("Invalid JSON body", StatusCode=400)
    return App.Json({
        "Echo":   Body,
        "Mode":   "async",
        "Method": Req.Method,
        "Path":   Req.Path,
        "Headers": {
            "ContentType": Req.ContentType,
            "Host":        Req.Host,
        },
    })


@App.Get("/status")
async def Status(Req):
    async def CheckDb():
        await asyncio.sleep(0)
        return {"Ok": True, "Records": DB.Table("users").Count() + DB.Table("products").Count() + DB.Table("orders").Count(), "Driver": DB.Driver}

    async def CheckCache():
        await asyncio.sleep(0)
        return {"Ok": True, "Sessions": App.Sessions.Count()}

    async def CheckSystem():
        await asyncio.sleep(0)
        return {"Ok": True, "CpuCount": os.cpu_count(), "Pid": os.getpid()}

    DbStatus, CacheStatus, SystemStatus = await App.Gather(CheckDb(), CheckCache(), CheckSystem())
    AllOk = all(S.get("Ok") for S in [DbStatus, CacheStatus, SystemStatus])

    return App.Json({
        "Status":   "healthy" if AllOk else "degraded",
        "Version":  "1.0.0",
        "Server":   f"{Host}:{Port}",
        "Services": {"Database": DbStatus, "Cache": CacheStatus, "System": SystemStatus},
        "Ts":       int(time.time()),
    })


@App.Get("/routes")
def Routes(Req):
    AllRoutes = [{"Pattern": R.Pattern, "Methods": R.Methods} for R in App.ListRoutes()]
    return App.Json({"Total": len(AllRoutes), "Routes": AllRoutes})


@App.Get("/logs")
def Logs(Req):
    Limit = max(1, min(int(Req.GetQuery("limit", 20)), 100))
    return App.Json({"Total": len(RequestLog), "Limit": Limit, "Logs": RequestLog[-Limit:][::-1]})


@App.Get("/db/stats")
def DbStats(Req):
    return App.Json({"DB": repr(DB), "Stats": DB.Stats(), "Tables": DB.Tables(), "Migrations": DB.MigrationStatus()})


@App.Get("/db/schema/<TableName>")
def DbSchema(Req):
    TableName = Req.PathParams.get("TableName", "")
    if not DB.TableExists(TableName):
        return App.Error(f"Table '{TableName}' not found", StatusCode=404)
    return App.Json({"Table": TableName, "Schema": DB.Schema(TableName)})


@App.Get("/users")
def GetUsers(Req):
    Query = DB.Table("users").OrderBy("id")
    if Req.GetQuery("role"):
        Query = Query.WhereEq("role", Req.GetQuery("role"))
    if Req.GetQuery("search"):
        Query = Query.WhereLike("name", f"%{Req.GetQuery('search')}%")
    return App.Json(Query.Paginate(Page=int(Req.GetQuery("page", 1)), PerPage=int(Req.GetQuery("per", 20))))


@App.Get("/users/<int:UserId>")
def GetUser(Req):
    UserId = int(Req.PathParams.get("UserId", 0))
    User   = DB.Table("users").WhereEq("id", UserId).First()
    if User is None:
        return App.Error(f"User {UserId} not found", StatusCode=404)
    return App.Json({"User": User})


@App.Post("/users", Middlewares=[RequireJson])
def CreateUser(Req):
    Body = Req.GetJson()
    if not Body or not Body.get("Name") or not Body.get("Email"):
        return App.Error("Fields 'Name' and 'Email' are required", StatusCode=400, Details={"Required": ["Name", "Email"]})
    if DB.Table("users").WhereEq("email", Body["Email"]).First():
        return App.Error(f"Email '{Body['Email']}' already exists", StatusCode=409)
    NewId = DB.InsertRow("users", {"name": Body["Name"], "email": Body["Email"], "role": Body.get("Role", "user"), "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return App.Json({"Message": "User created", "User": DB.Table("users").WhereEq("id", NewId).First()}, StatusCode=201)


@App.Put("/users/<int:UserId>", Middlewares=[RequireJson])
def UpdateUser(Req):
    UserId = int(Req.PathParams.get("UserId", 0))
    if not DB.Table("users").WhereEq("id", UserId).First():
        return App.Error(f"User {UserId} not found", StatusCode=404)
    Body    = Req.GetJson()
    Updates = {K: V for K, V in {"name": Body.get("Name"), "email": Body.get("Email"), "role": Body.get("Role")}.items() if V}
    if Updates:
        DB.Table("users").WhereEq("id", UserId).Update(Updates)
    return App.Json({"Message": "User updated", "User": DB.Table("users").WhereEq("id", UserId).First()})


@App.Delete("/users/<int:UserId>")
def DeleteUser(Req):
    UserId = int(Req.PathParams.get("UserId", 0))
    if not DB.Table("users").WhereEq("id", UserId).First():
        return App.Error(f"User {UserId} not found", StatusCode=404)
    DB.Table("users").WhereEq("id", UserId).Delete()
    return App.Json({"Message": f"User {UserId} deleted"})


@App.Get("/products")
def GetProducts(Req):
    Query = DB.Table("products").OrderBy("id")
    if Req.GetQuery("min_price"):
        Query = Query.Where("price >= ?", float(Req.GetQuery("min_price")))
    if Req.GetQuery("max_price"):
        Query = Query.Where("price <= ?", float(Req.GetQuery("max_price")))
    return App.Json(Query.Paginate(Page=int(Req.GetQuery("page", 1)), PerPage=int(Req.GetQuery("per", 20))))


@App.Get("/products/<int:ProductId>")
def GetProduct(Req):
    ProductId = int(Req.PathParams.get("ProductId", 0))
    Product   = DB.Table("products").WhereEq("id", ProductId).First()
    if Product is None:
        return App.Error(f"Product {ProductId} not found", StatusCode=404)
    return App.Json({"Product": Product})


@App.Post("/orders", Middlewares=[RequireJson])
async def CreateOrder(Req):
    Body      = Req.GetJson()
    UserId    = Body.get("UserId")
    ProductId = Body.get("ProductId")
    Qty       = int(Body.get("Quantity", 1))

    if not UserId or not ProductId:
        return App.Error("Fields 'UserId' and 'ProductId' are required", StatusCode=400)

    async def ValidateUser():
        await asyncio.sleep(0)
        return DB.Table("users").WhereEq("id", UserId).First()

    async def ValidateProduct():
        await asyncio.sleep(0)
        return DB.Table("products").WhereEq("id", ProductId).First()

    User, Product = await App.Gather(ValidateUser(), ValidateProduct())

    if User is None:
        return App.Error(f"User {UserId} not found", StatusCode=404)
    if Product is None:
        return App.Error(f"Product {ProductId} not found", StatusCode=404)
    if Product["stock"] < Qty:
        return App.Error("Insufficient stock", StatusCode=409, Details={"Available": Product["stock"], "Requested": Qty})

    with DB.Transaction() as Tx:
        Tx.Execute("UPDATE products SET stock = stock - ? WHERE id = ?", [Qty, ProductId])
        OrderId = Tx.Insert(
            "INSERT INTO orders (user_id, product_id, quantity, total, status, created) VALUES (?, ?, ?, ?, 'confirmed', ?)",
            [UserId, ProductId, Qty, round(Product["price"] * Qty, 2), time.strftime("%Y-%m-%dT%H:%M:%S")]
        )

    return App.Json({"Message": "Order created", "Order": DB.Table("orders").WhereEq("id", OrderId).First()}, StatusCode=201)


@App.Get("/orders")
def GetOrders(Req):
    Query = DB.Table("orders").OrderBy("id", "DESC")
    if Req.GetQuery("UserId"):
        Query = Query.WhereEq("user_id", int(Req.GetQuery("UserId")))
    return App.Json(Query.Paginate(Page=int(Req.GetQuery("page", 1)), PerPage=int(Req.GetQuery("per", 20))))


@App.Post("/auth/login", Middlewares=[RequireJson])
def Login(Req):
    Body  = Req.GetJson()
    User  = DB.Table("users").WhereEq("email", Body.get("Email", "")).First()
    if User is None:
        return App.Error("Invalid credentials", StatusCode=401)
    Token    = App.CreateJwt({"UserId": User["id"], "Role": User["role"], "Email": User["email"]}, ExpiresIn=3600)
    Response = App.Json({"Message": "Login successful", "Token": Token, "User": User})
    App.SaveSession(Response, {"UserId": User["id"], "Role": User["role"]})
    return Response


@App.Get("/auth/me")
def Me(Req):
    AuthHeader = Req.Authorization
    if not AuthHeader.startswith("Bearer "):
        return App.Error("Authorization header required", StatusCode=401)
    Payload = App.DecodeJwt(AuthHeader[7:])
    if Payload is None:
        return App.Error("Invalid or expired token", StatusCode=401)
    User = DB.Table("users").WhereEq("id", Payload.get("UserId")).First()
    if User is None:
        return App.Error("User not found", StatusCode=404)
    return App.Json({"User": User, "TokenPayload": Payload})


@App.Post("/auth/logout")
def Logout(Req):
    _, SessionId = App.GetSession(Req)
    if SessionId:
        App.Sessions.Delete(SessionId)
    return App.Json({"Message": "Logged out"})


@App.Get("/stream")
def Stream(Req):
    Count = max(1, min(int(Req.GetQuery("count", 5)), 20))
    def EventGenerator():
        import json
        for i in range(Count):
            yield f"data: {json.dumps({'Event': i + 1, 'Ts': int(time.time()), 'Value': random.randint(1, 100)})}\n\n"
            time.sleep(0.4)
        yield 'data: {"Event": "done"}\n\n'
    return App.Stream(EventGenerator, ContentType="text/event-stream")


@App.Get("/timeout-demo")
async def TimeoutDemo(Req):
    Seconds = float(Req.GetQuery("wait", 1.0))
    Limit   = float(Req.GetQuery("limit", 2.0))
    async def SlowTask():
        await asyncio.sleep(Seconds)
        return {"Result": "completed", "Waited": Seconds}
    try:
        Result = await App.Timeout(SlowTask(), Seconds=Limit)
        return App.Json({"Status": "ok", "Data": Result})
    except Exception:
        return App.Error(f"Task timed out after {Limit}s", StatusCode=408, Details={"Limit": Limit, "Requested": Seconds})


@App.Get("/context-demo")
def ContextDemo(Req):
    RequestContext.Set("RequestId", f"req-{random.randint(1000, 9999)}")
    RequestContext.Set("UserIp",    Req.RemoteIp)
    RequestContext.Set("Path",      Req.Path)
    CtxData = RequestContext.All()
    RequestContext.Clear()
    return App.Json({"Context": CtxData, "Cleared": True})


@App.Route("/multi", Methods=["GET", "POST", "PUT"])
def MultiMethod(Req):
    return App.Json({"Method": Req.Method, "Path": Req.Path, "Query": Req.QueryParams, "HasBody": len(Req.Body) > 0, "ContentType": Req.ContentType or None, "RemoteIp": Req.RemoteIp})


@App.Get("/info")
def Info(Req):
    return App.Json({"App": repr(App), "DB": repr(DB), "Paths": App.GetPaths(), "Routes": len(App.ListRoutes()), "Sessions": App.Sessions.Count(), "Stats": App.GetStats()})


ApiRouter = HellcatRouter(Prefix="/api/v1")


@ApiRouter.Get("/health")
def ApiHealth(Req):
    return App.Json({"Status": "ok", "Version": "v1", "Ts": int(time.time())})


@ApiRouter.Get("/summary")
async def ApiSummary(Req):
    async def CountUsers():
        await asyncio.sleep(0)
        return DB.Table("users").Count()
    async def CountOrders():
        await asyncio.sleep(0)
        return DB.Table("orders").Count()
    async def CountProducts():
        await asyncio.sleep(0)
        return DB.Table("products").Count()
    Users, Orders, Products = await App.Gather(CountUsers(), CountOrders(), CountProducts())
    return App.Json({"Users": Users, "Orders": Orders, "Products": Products, "LogEntries": len(RequestLog), "DBDriver": DB.Driver})


App.Include(ApiRouter)


if __name__ == "__main__":
    os.system("cls" if os.name == "nt" else "clear")
    App.Run(
        Host=Host,
        Port=Port,
        # SslCertFile=CertFile,
        # SslKeyFile=KeyFile,
        # HttpRedirectPort=9926,
        Asynchronous=True,
        Debug=False,
        Logger=False,
    )
