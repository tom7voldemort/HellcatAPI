<div align="center">

```
██╗  ██╗███████╗██╗     ██╗      ██████╗ █████╗ ████████╗ █████╗ ██████╗ ██╗
██║  ██║██╔════╝██║     ██║     ██╔════╝██╔══██╗╚══██╔══╝██╔══██╗██╔══██╗██║
███████║█████╗  ██║     ██║     ██║     ███████║   ██║   ███████║██████╔╝██║
██╔══██║██╔══╝  ██║     ██║     ██║     ██╔══██║   ██║   ██╔══██║██╔═══╝ ██║
██║  ██║███████╗███████╗███████╗╚██████╗██║  ██║   ██║   ██║  ██║██║     ██║
╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝     ╚═╝
```

**A lightweight, zero-dependency HTTP API framework for Python.**  
Built from raw sockets up — no WSGI, no ASGI, no third-party libraries.

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen?style=flat-square)]()
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Termux%20%7C%20Android-orange?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/XTM26/HellcatAPI?style=flat-square&color=yellow)](https://github.com/XTM26/HellcatAPI/stargazers)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Routing](#routing)
- [Request Object](#request-object)
- [Response Types](#response-types)
- [Middleware](#middleware)
- [Template Engine](#template-engine)
- [Database](#database)
- [Session Management](#session-management)
- [JWT Utilities](#jwt-utilities)
- [Async Support](#async-support)
- [Static File Serving](#static-file-serving)
- [HTTPS and SSL](#https-and-ssl)
- [Sub-Routers](#sub-routers)
- [Custom Error Handlers](#custom-error-handlers)
- [Request Context](#request-context)
- [Server Configuration](#server-configuration)
- [License](#license)

---

## Overview

HellcatAPI speaks HTTP directly over TCP sockets. It handles everything from request parsing and routing to response serialisation, middleware pipelines, template rendering, session management, and database access — with no external dependencies beyond the Python standard library.

It supports synchronous and asynchronous route handlers, a built-in middleware collection, a Jinja2-inspired template engine, HMAC-signed JWT tokens, a connection-pooled database layer (SQLite, PostgreSQL, MySQL, MongoDB), and HTTPS via TLS — all in plain Python.

---

## Requirements

- Python 3.8 or later
- No external packages required

---

## Installation

```bash
git clone https://github.com/XTM26/HellcatAPI.git
cd HellcatAPI
python TestApi.py
```

No `pip install` step is required.

---

## Project Structure

```
HellcatAPI/
├── cores/
│   ├── App/
│   │   └── HellcatApp.py          # Main application class & lifecycle
│   ├── Async/
│   │   └── HellcatAsync.py        # Async handler detection, event loop management
│   ├── Context/
│   │   └── HellcatContext.py      # Session store, JWT utility, thread-local context
│   ├── DB/
│   │   └── HellcatDB.py           # Database abstraction layer with connection pooling
│   ├── Middleware/
│   │   └── HellcatMiddleware.py   # Built-in middleware collection
│   ├── Request/
│   │   └── HellcatRequest.py      # HTTP request parser (headers, body, form, multipart)
│   ├── Response/
│   │   └── HellcatResponse.py     # HTTP response builder and subclass hierarchy
│   ├── Router/
│   │   └── HellcatRouter.py       # URL router with pattern compilation & middleware chaining
│   ├── Server/
│   │   └── HellcatServer.py       # TCP socket server, connection handler, logger
│   ├── Template/
│   │   └── HellcatTemplate.py     # Template engine (no external dependencies)
│   └── __init__.py                # Public API surface and module entry point
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
├── templates/
│   └── index.html
├── TestApi.py                     # Example application & test routes
├── .gitignore
└── README.md
```

---

## Quick Start

```python
from cores.App.HellcatApp import HellcatApp

App = HellcatApp()

@App.Get("/")
def Index(Req):
    return App.Json({"Message": "Hello from HellcatAPI"})

@App.Post("/echo")
def Echo(Req):
    Body = Req.GetJson()
    if Body is None:
        return App.Error("Invalid JSON", StatusCode=400)
    return App.Json({"Echo": Body})

if __name__ == "__main__":
    App.Run(Host="0.0.0.0", Port=9926)
```

---

## Routing

### HTTP Method Decorators

```python
@App.Get("/users")
def GetUsers(Req): ...

@App.Post("/users")
def CreateUser(Req): ...

@App.Put("/users/<Id>")
def UpdateUser(Req): ...

@App.Delete("/users/<Id>")
def DeleteUser(Req): ...

@App.Patch("/users/<Id>")
def PatchUser(Req): ...

@App.Any("/webhook")
def AnyMethod(Req): ...
```

### Dynamic Path Parameters

```python
@App.Get("/user/<UserId>")
def GetUser(Req):
    UserId = Req.PathParams["UserId"]
    return App.Json({"Id": UserId})

@App.Get("/post/<int:PostId>")
def GetPost(Req):
    PostId = int(Req.PathParams["PostId"])
    return App.Json({"PostId": PostId})
```

### Multi-Method Routes

```python
@App.Route("/login", Methods=["GET", "POST"])
def Login(Req):
    if Req.Method == "GET":
        return App.Render("login.html")
    return App.Json({"Token": "..."})
```

---

## Request Object

Each handler receives a `HellcatRequest` instance with the following interface.

| Attribute / Method | Description |
|---|---|
| `Req.Method` | HTTP method string (`GET`, `POST`, etc.) |
| `Req.Path` | Decoded URL path |
| `Req.PathParams` | Dict of dynamic path segments |
| `Req.QueryParams` | Dict of query string parameters |
| `Req.Headers` | Dict of lowercase header names to values |
| `Req.Cookies` | Dict of cookie name/value pairs |
| `Req.Body` | Raw request body as `bytes` |
| `Req.Form` | URL-encoded or multipart form fields |
| `Req.Files` | Uploaded files as `HellcatUploadedFile` objects |
| `Req.RemoteIp` | Client IP address string |
| `Req.ContentType` | Value of the Content-Type header |
| `Req.UserAgent` | Value of the User-Agent header |
| `Req.Host` | Value of the Host header |
| `Req.Authorization` | Value of the Authorization header |
| `Req.IsJson` | `True` if Content-Type is `application/json` |
| `Req.IsForm` | `True` if Content-Type is `application/x-www-form-urlencoded` |
| `Req.IsMultipart` | `True` if Content-Type is `multipart/form-data` |
| `Req.GetHeader(Name)` | Case-insensitive header lookup |
| `Req.GetQuery(Key, Default)` | Query param lookup with optional default |
| `Req.GetForm(Key, Default)` | Form field lookup with optional default |
| `Req.GetJson()` | Parses body as JSON, returns `None` on failure |
| `Req.RequireJson()` | Like `GetJson()` but raises on parse failure |
| `Req.GetFile(FieldName)` | Returns uploaded file or `None` |
| `Req.RequireFile(FieldName)` | Returns uploaded file or raises |

### File Uploads

```python
@App.Post("/upload")
def Upload(Req):
    File = Req.RequireFile("Avatar")
    File.Save(f"/uploads/{File.Filename}")
    return App.Json({"Saved": File.Filename, "Size": File.Size})
```

---

## Response Types

All response helpers return an object that HellcatAPI serialises and sends automatically.

```python
App.Json({"Key": "Value"}, StatusCode=200)
App.Html("<h1>Hello</h1>", StatusCode=200)
App.Text("plain text")
App.Redirect("/new-path", StatusCode=302)
App.File("/path/to/file.pdf", DownloadAs="report.pdf")
App.Error("Not authorised", StatusCode=401)
App.Error("Validation failed", StatusCode=400, Details={"Required": ["Name"]})
App.Stream(GeneratorFunc, ContentType="text/event-stream")
App.Render("template.html", {"Key": "Value"})
```

### Setting Headers and Cookies

```python
@App.Get("/set-cookie")
def SetCookie(Req):
    Resp = App.Json({"Ok": True})
    Resp.SetHeader("X-Custom-Header", "value")
    Resp.SetCookie("Session", "abc123", MaxAge=3600, HttpOnly=True)
    return Resp
```

### Tuple Shorthand

Handlers may return a `(body, status)` or `(body, status, headers)` tuple:

```python
@App.Get("/created")
def Created(Req):
    return {"Id": 1}, 201
```

---

## Middleware

### Global Middleware

```python
App.UseCors(AllowedOrigins=["https://example.com"], AllowCredentials=True)
App.UseRateLimit(MaxRequests=100, WindowSeconds=60)
App.UseSecurityHeaders()
App.UseGzip(MinSizeBytes=1024)
App.UseBodySizeLimit(MaxBytes=5 * 1024 * 1024)
```

### Per-Route Middleware

```python
from cores.Middleware.HellcatMiddleware import HellcatBearerAuthMiddleware

AuthMw = HellcatBearerAuthMiddleware(ValidTokens=["my-secret-token"])

@App.Get("/admin", Middlewares=[AuthMw])
def AdminPanel(Req):
    return App.Json({"Panel": "admin"})
```

### Custom Middleware

```python
def LoggingMiddleware(Request, Next):
    print(f"Incoming: {Request.Method} {Request.Path}")
    Response = Next(Request)
    print(f"Outgoing: {Response.StatusCode}")
    return Response

App.UseMiddleware(LoggingMiddleware)
```

Async middleware is also supported:

```python
async def AsyncLoggingMiddleware(Request, Next):
    Response = await Next(Request)
    return Response
```

### Built-in Middleware

| Class | Purpose |
|---|---|
| `HellcatCorsMiddleware` | CORS headers and preflight handling |
| `HellcatRateLimitMiddleware` | Per-IP sliding window rate limiting |
| `HellcatBasicAuthMiddleware` | HTTP Basic Authentication |
| `HellcatBearerAuthMiddleware` | Bearer token authentication (static list or custom validator) |
| `HellcatBodySizeLimitMiddleware` | Reject oversized request bodies (413) |
| `HellcatGzipMiddleware` | Gzip compression for responses above a size threshold |
| `HellcatSecurityHeadersMiddleware` | X-Content-Type-Options, X-Frame-Options, CSP, and related headers |
| `HellcatCsrfMiddleware` | HMAC-based CSRF cookie/header validation |
| `HellcatJsonValidatorMiddleware` | Enforce required fields and type schema on JSON bodies |

---

## Template Engine

HellcatAPI includes a Jinja2-inspired template engine backed entirely by the standard library.

### Setup

```python
App = HellcatApp(TemplateDir="templates")
```

Template files are resolved relative to the script that instantiates `HellcatApp`, not the current working directory.

### Rendering

```python
@App.Get("/")
def Home(Req):
    return App.Render("index.html", {"Title": "Home", "Items": [1, 2, 3]})
```

### Template Syntax

```html
<!-- Variable interpolation (HTML-escaped by default) -->
<h1>{{ Title }}</h1>

<!-- Raw output, no escaping -->
<div>{{ HtmlContent | raw }}</div>

<!-- Conditionals -->
{% if User %}
  <p>Welcome, {{ User.Name }}</p>
{% elif Guest %}
  <p>Hello, guest.</p>
{% else %}
  <p>Please log in.</p>
{% endif %}

<!-- Loops -->
{% for Item in Items %}
  <li>{{ Item }}</li>
{% endfor %}

<!-- Include partials -->
{% include "partials/nav.html" %}

<!-- Template inheritance -->
{% extends "base.html" %}
{% block Content %}
  <p>Child content here.</p>
{% endblock %}

<!-- Comments (stripped from output) -->
{# This will not appear in the rendered HTML #}
```

### Rendering a String Directly

```python
Html = App.RenderString("<p>Hello {{ Name }}</p>", {"Name": "World"})
```

---

## Database

HellcatAPI includes `HellcatDB`, a connection-pooled database layer that supports SQLite, PostgreSQL, MySQL, and MongoDB. The driver is detected automatically from the connection string.

### Connecting

```python
from cores.DB.HellcatDB import HellcatDB

# SQLite
DB = HellcatDB(DB="app.db", PoolSize=10)

# PostgreSQL
DB = HellcatDB(DB="postgres://user:pass@localhost/mydb")

# MySQL
DB = HellcatDB(DB="mysql://user:pass@localhost/mydb")
```

### Auto-Migration

Pass a dictionary of ordered migration scripts. Each key is a migration name; scripts that have already run are skipped automatically.

```python
DB = HellcatDB(
    DB="app.db",
    AutoMigrate={
        "001_CreateUsers": """
            CREATE TABLE users (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                email   TEXT NOT NULL UNIQUE,
                created TEXT NOT NULL
            )
        """,
    },
)
```

### Query Builder

```python
# Fetch all rows
Users = DB.Table("users").All()

# Filter, order, and paginate
Result = DB.Table("users").WhereEq("role", "admin").OrderBy("id").Paginate(Page=1, PerPage=20)

# First matching row
User = DB.Table("users").WhereEq("email", "tom@example.com").First()

# Custom condition
Products = DB.Table("products").Where("price >= ?", 50.0).All()

# Pattern match
Matches = DB.Table("users").WhereLike("name", "%tom%").All()

# Count
Total = DB.Table("users").Count()

# Update
DB.Table("users").WhereEq("id", 1).Update({"name": "New Name"})

# Delete
DB.Table("users").WhereEq("id", 1).Delete()
```

### Inserting Rows

```python
NewId = DB.InsertRow("users", {
    "name": "Alice",
    "email": "alice@example.com",
    "created": "2026-01-01T00:00:00",
})
```

### Transactions

```python
with DB.Transaction() as Tx:
    Tx.Execute("UPDATE products SET stock = stock - ? WHERE id = ?", [1, ProductId])
    OrderId = Tx.Insert(
        "INSERT INTO orders (user_id, product_id, total, created) VALUES (?, ?, ?, ?)",
        [UserId, ProductId, 49.99, "2026-01-01T00:00:00"],
    )
```

### Introspection

```python
DB.Tables()              # list all table names
DB.Schema("users")       # column definitions for a table
DB.TableExists("users")  # bool
DB.Stats()               # pool stats
DB.MigrationStatus()     # which migrations have run
```

### Error Types

| Exception | Raised When |
|---|---|
| `HellcatDBConnectionError` | Cannot connect to the database |
| `HellcatDBQueryError` | SQL execution fails |
| `HellcatDBNotFoundError` | A required record does not exist |
| `HellcatDBPoolExhaustedError` | All pool connections are in use |
| `HellcatDBMigrationError` | A migration script fails |
| `HellcatDBDriverError` | The driver cannot be detected from the connection string |

---

## Session Management

HellcatAPI provides an in-memory session store with automatic TTL expiry.

```python
@App.Post("/login")
def Login(Req):
    Data, SessionId = App.GetSession(Req)
    Data["UserId"] = 42
    Resp = App.Json({"Ok": True})
    App.SaveSession(Resp, Data, SessionId)
    return Resp

@App.Get("/profile")
def Profile(Req):
    Data, _ = App.GetSession(Req)
    UserId = Data.get("UserId")
    if not UserId:
        return App.Error("Not authenticated", StatusCode=401)
    return App.Json({"UserId": UserId})

@App.Post("/logout")
def Logout(Req):
    _, SessionId = App.GetSession(Req)
    if SessionId:
        App.Sessions.Delete(SessionId)
    return App.Json({"Message": "Logged out"})
```

> Session data is stored in memory. For multi-worker deployments or server restarts, replace with a persistent store such as Redis. The default TTL is 3600 seconds and is configurable on `HellcatSessionStore` directly.

---

## JWT Utilities

```python
# Create a signed token
Token = App.CreateJwt({"UserId": 1, "Role": "admin"}, ExpiresIn=3600)

# Decode and verify
Payload = App.DecodeJwt(Token)
if Payload is None:
    return App.Error("Invalid or expired token", StatusCode=401)
```

Tokens are signed with HMAC-SHA256 using the `SecretKey` passed to `HellcatApp`. Always change the default secret before deploying to production:

```python
App = HellcatApp(SecretKey="your-strong-production-secret")
```

---

## Async Support

Async route handlers work transparently alongside synchronous ones.

```python
import asyncio

@App.Get("/async-ping")
async def AsyncPing(Req):
    await asyncio.sleep(0)
    return App.Json({"Pong": True})
```

### Concurrent Sub-tasks Within a Handler

```python
@App.Get("/dashboard")
async def Dashboard(Req):
    async def FetchUser():
        await asyncio.sleep(0.01)
        return {"Id": 1, "Name": "Alice"}

    async def FetchStats():
        await asyncio.sleep(0.01)
        return {"Requests": 500}

    User, Stats = await App.Gather(FetchUser(), FetchStats())
    return App.Json({"User": User, "Stats": Stats})
```

### Timeout

```python
@App.Get("/slow")
async def Slow(Req):
    Result = await App.Timeout(SomeSlowCoroutine(), Seconds=5)
    return App.Json(Result)
```

To run the entire server in async mode:

```python
App.Run(Asynchronous=True)
```

---

## Static File Serving

```python
App = HellcatApp(StaticDir="static", StaticUrl="/static")
```

Files in the `static/` directory are served at the `/static/` URL prefix. The directory structure is preserved — `static/css/style.css` is accessible at `/static/css/style.css`. Directory traversal is blocked. Requests to a directory path automatically serve `index.html` if present.

```python
# Swap the static directory at runtime
App.SetStaticDir("static_v2", NewUrl="/static")
```

---

## HTTPS and SSL

```python
App.Run(
    Host="0.0.0.0",
    Port=443,
    SslCertFile="certs/cert.pem",
    SslKeyFile="certs/key.pem",
    HttpRedirectPort=80,  # optional: redirect HTTP traffic to HTTPS automatically
)
```

TLS 1.2 is the minimum version enforced. HTTP clients connecting to the HTTPS port receive a `426 Upgrade Required` response.

---

## Sub-Routers

Sub-routers allow modular route organisation with optional path prefixes.

```python
from cores.Router.HellcatRouter import HellcatRouter

ApiRouter = HellcatRouter(Prefix="/api/v1")

@ApiRouter.Get("/users")
def GetUsers(Req):
    return App.Json({"Users": []})

@ApiRouter.Post("/users")
def CreateUser(Req):
    return App.Json({"Created": True}, StatusCode=201)

App.Include(ApiRouter)
```

Sub-routers can carry their own middleware and error handlers, which are merged into the main application on `Include()`.

---

## Custom Error Handlers

```python
@App.ErrorHandler(404)
def NotFound(Req, Error=None):
    return App.Json({"Error": "Page not found"}, StatusCode=404)

@App.ErrorHandler(405)
def MethodNotAllowed(Req, Error=None):
    return App.Json({"Error": "Method not allowed"}, StatusCode=405)

@App.ErrorHandler(500)
def InternalError(Req, Error=None):
    return App.Json({"Error": "Something went wrong"}, StatusCode=500)
```

---

## Request Context

`RequestContext` is a thread-local store for passing data within a single request lifecycle, similar to `flask.g`.

```python
from cores.Context.HellcatContext import RequestContext

def AuthMiddleware(Request, Next):
    Token = Request.GetHeader("Authorization", "")
    if Token:
        RequestContext.Set("UserId", 42)
    return Next(Request)

@App.Get("/me")
def Me(Req):
    UserId = RequestContext.Get("UserId")
    return App.Json({"UserId": UserId})
```

The context is cleared automatically at the start of each new request.

---

## Server Configuration

### `HellcatApp()` Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `TemplateDir` | `str` | `"templates"` | Template directory name or path |
| `StaticDir` | `str` | `None` | Static file directory (disabled if `None`) |
| `StaticUrl` | `str` | `"/static"` | URL prefix for static files |
| `SecretKey` | `str` | built-in default | Secret for JWT signing and CSRF tokens |
| `Debug` | `bool` | `False` | Debug mode |
| `AutoCreateDirs` | `bool` | `False` | Create `TemplateDir` and `StaticDir` automatically if absent |

### `App.Run()` Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `Host` | `str` | `"0.0.0.0"` | Bind address |
| `Port` | `int` | `9926` | TCP port |
| `Workers` | `int` | `cpu_count x 4` | Thread pool size |
| `SslCertFile` | `str` | `None` | Path to PEM certificate |
| `SslKeyFile` | `str` | `None` | Path to PEM private key |
| `HttpRedirectPort` | `int` | `None` | HTTP port to redirect from when HTTPS is active |
| `Blocking` | `bool` | `True` | Block the main thread while the server is running |
| `Debug` | `bool` | `False` | Include error details in 500 responses |
| `Asynchronous` | `bool` | `False` | Force all handlers through the async event loop |
| `Logger` | `bool` | `True` | Enable request log and per-second stats ticker output |

### Runtime Inspection

```python
App.ListRoutes()   # list of all registered HellcatRoute objects
App.GetPaths()     # dict of resolved TemplateDir, StaticDir, CallerDir
App.GetStats()     # dict of uptime, request count, worker count, and more
```

---

## License

HellcatAPI is developed and maintained by [XTM26](https://github.com/XTM26).  
Released under the MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

*Built with obsession and zero dependencies.*  
**HellcatAPI — raw power, no bloat.**

</div>

<p align="center">&copy; 2026 XTM26</p>