<div align="center">

```
 _   _      _ _           _      _    ____ ___ 
| | | | ___| | | ___ __ _| |_   / \  |  _ \_ _|
| |_| |/ _ \ | |/ __/ _` | __| / _ \ | |_) | | 
|  _  |  __/ | | (_| (_| | |_ / ___ \|  __/| | 
|_| |_|\___|_|_|\___\__,_|\__/_/   \_\_|  |___|
```

# HellcatAPI

**A lightweight, async-first Python web framework built entirely on standard library modules.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Termux%20%7C%20Android-orange?style=flat-square)]()
[![Status](https://img.shields.io/badge/Status-Active%20Development-yellow?style=flat-square)]()
[![Stars](https://img.shields.io/github/stars/0xTM7/HellcatAPI?style=flat-square)](https://github.com/0xTM7/HellcatAPI/stargazers)

*No pip. No dependencies. Just Python.*

</div>

---

## What is HellcatAPI?

HellcatAPI is a custom Python web framework handcrafted from scratch using only Python's built-in standard library — no external packages required. It features a fully async request pipeline, a modular middleware system, a clean router with parameter support, and a template engine — all wired together in a minimal, readable codebase.

Built and maintained on Termux (Android), HellcatAPI is proof that you don't need a bloated ecosystem to ship a capable web framework.

---

## Features

| Feature | Description |
|---|---|
| **Zero Dependencies** | Runs entirely on Python's standard library |
| **Async Core** | Built on `asyncio` with proper event loop management |
| **Middleware Pipeline** | Stack-based middleware with full request/response control |
| **Router** | Path-based routing with dynamic parameter extraction |
| **Template Engine** | Simple HTML template rendering with context injection |
| **Static File Serving** | Serve CSS, JS, and assets out of the box |
| **CORS Support** | Built-in CORS middleware |
| **Context Object** | Clean per-request context passing through the pipeline |
| **Termux Compatible** | Designed and tested on Android via Termux |

---

## Project Structure

```
HellcatAPI/
├── cores/
│   ├── HellcatApp.py          # Application entry point & lifecycle
│   ├── HellcatAsync.py        # Async utilities & event loop management
│   ├── HellcatContext.py      # Per-request context object
│   ├── HellcatMiddleware.py   # Middleware base & pipeline
│   ├── HellcatRequest.py      # HTTP request parsing
│   ├── HellcatResponse.py     # HTTP response builder
│   ├── HellcatRouter.py       # Route registration & matching
│   ├── HellcatServer.py       # TCP server & connection handler
│   ├── HellcatTemplate.py     # HTML template rendering
│   └── __init__.py            # Package exports
├── static/                    # Static assets (CSS, JS, images)
├── templates/                 # HTML template files
├── TestApi.py                 # Example application & test routes
├── .gitignore
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.10 or higher
- No pip install required

### Clone the Repository

```bash
git clone https://github.com/0xTM7/HellcatAPI.git
cd HellcatAPI
```

### Run the Example App

```bash
python TestApi.py
```

The server will start on `http://0.0.0.0:8000` by default.

---

## Usage

### Minimal Application

```python
from cores import HellcatApp, HellcatRouter, HellcatRequest, HellcatResponse

Router = HellcatRouter()

@Router.Get("/")
async def Index(Request: HellcatRequest, Response: HellcatResponse):
    Response.Json({"Message": "Hello from HellcatAPI"})

App = HellcatApp(Router=Router)
App.Run(Host="0.0.0.0", Port=8000)
```

### Route Parameters

```python
@Router.Get("/Users/{UserId}")
async def GetUser(Request: HellcatRequest, Response: HellcatResponse):
    UserId = Request.Params.get("UserId")
    Response.Json({"UserId": UserId})
```

### Returning HTML Templates

```python
@Router.Get("/Home")
async def Home(Request: HellcatRequest, Response: HellcatResponse):
    Response.Template("index.html", Context={"Title": "HellcatAPI"})
```

### Custom Middleware

```python
from cores import HellcatMiddleware, HellcatContext

class LoggerMiddleware(HellcatMiddleware):
    async def Call(self, Context: HellcatContext, Next):
        print(f"[HellcatAPI] {Context.Request.Method} {Context.Request.Path}")
        await Next(Context)

App = HellcatApp(Router=Router, Middleware=[LoggerMiddleware()])
```

---

## Core Modules

### `HellcatApp`
The top-level application object. Wires together the router, middleware stack, and server. Call `.Run()` to start listening.

### `HellcatServer`
Low-level TCP server based on `asyncio`. Handles incoming connections and dispatches them through the framework pipeline.

### `HellcatRouter`
Registers route handlers for HTTP methods (`Get`, `Post`, `Put`, `Delete`, `Patch`). Supports dynamic path segments using `{Param}` syntax.

### `HellcatMiddleware`
Base class for middleware. Override the `Call(Context, Next)` method. Middleware is executed in registration order and must explicitly call `await Next(Context)` to continue the chain.

### `HellcatRequest`
Parses raw HTTP request data into a structured object. Exposes `Method`, `Path`, `Headers`, `Params`, `Query`, and `Body`.

### `HellcatResponse`
Builder for HTTP responses. Provides `.Json()`, `.Html()`, `.Template()`, `.Status()`, and `.Header()` methods.

### `HellcatContext`
A per-request container that holds both the `Request` and `Response` objects, passed through the entire middleware and handler chain.

### `HellcatTemplate`
Renders HTML templates from the `templates/` directory, supporting simple variable substitution via context dictionaries.

### `HellcatAsync`
Async utilities for managing the event loop safely, including helpers to resolve conflicts in threaded environments.

---

## Style Conventions

HellcatAPI enforces a consistent internal coding style across the entire codebase:

- All identifiers, class names, method names, and string keys use **PascalCase**
- No underscore-prefixed names (no `_private` style)
- No inline `#` comments — documentation via `""""""` docstrings only
- Strict separation of concerns across module files

---

## Roadmap

- [x] Async request/response pipeline
- [x] Middleware stack
- [x] Dynamic routing with path parameters
- [x] Template rendering
- [x] Static file serving
- [x] CORS middleware
- [ ] Form data parsing
- [ ] File upload support
- [ ] WebSocket support
- [ ] CLI runner (`hellcat run`)
- [ ] Auto-reload on file change
- [ ] Request validation layer
- [ ] OpenAPI / Swagger documentation generation

---

## Running on Termux (Android)

HellcatAPI is built to run smoothly inside Termux without any native extensions.

```bash
pkg update && pkg upgrade
pkg install python git
git clone https://github.com/0xTM7/HellcatAPI.git
cd HellcatAPI
python TestApi.py
```

Access from your local network at `http://<your-device-ip>:8000`.

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b Feature/YourFeature`
3. Follow the project's PascalCase style conventions
4. Commit your changes: `git commit -m "Add YourFeature"`
5. Push and open a Pull Request

Please open an issue first for major changes so we can discuss direction before you write code.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

Built with obsession and zero dependencies by [0xTM7](https://github.com/0xTM7)

*HellcatAPI — raw power, no bloat.*

</div>
