import socket
import ssl
import threading
import os
import time
import traceback
import sys
from concurrent.futures import ThreadPoolExecutor

from cores.Request.HellcatRequest import HellcatRequestParser
from cores.Response.HellcatResponse import (
    HellcatResponse,
    HellcatHtmlResponse,
    HellcatJsonResponse,
    HellcatErrorResponse,
    HellcatFileResponse,
    HellcatStreamResponse,
)
from cores.Router.HellcatRouter import HellcatRouter
from cores.Context.HellcatContext import RequestContext
from cores.Async.HellcatAsync import (
    CallHandler,
    RunAsyncPipeline,
    HasAnyAsync,
    IsCoroutineFunction,
)

MaxRequestSize = 64 * 1024 * 1024
ReadChunkSize = 8192
SocketTimeout = 10
KeepAliveTimeout = 5
DefaultHost = "0.0.0.0"
DefaultPort = 9926
Version = "1.0.0"


class HellcatServerError(Exception):
    pass


class HellcatSocketError(HellcatServerError):
    pass


class HellcatSslError(HellcatServerError):
    pass


class HellcatRequestParseError(HellcatServerError):
    pass


class HellcatResponseBuildError(HellcatServerError):
    pass


class HellcatDispatchError(HellcatServerError):
    pass


class HellcatStaticFileError(HellcatServerError):
    pass


class HellcatLogger:
    Reset = "\033[0m"
    Bold = "\033[1m"
    Dim = "\033[2m"
    Green = "\033[92m"
    Yellow = "\033[93m"
    Red = "\033[91m"
    Cyan = "\033[96m"
    Gray = "\033[90m"
    Blue = "\033[94m"
    Purple = "\033[95m"
    White = "\033[97m"
    Orange = "\033[38;5;214m"

    MethodColors = {
        "GET": "\033[94m",
        "POST": "\033[92m",
        "PUT": "\033[93m",
        "DELETE": "\033[91m",
        "PATCH": "\033[95m",
        "OPTIONS": "\033[96m",
        "HEAD": "\033[90m",
        "TRACE": "\033[38;5;208m",
        "CONNECT": "\033[38;5;172m",
        "ANY": "\033[38;5;214m",
    }

    def __init__(self, Name="HellcatAPI", Silent=False, EnableDebug=False):
        self.Name = Name
        self.Silent = Silent
        self.EnableDebug = EnableDebug
        self.Lock = threading.Lock()
        self.StatsTicker = None
        self.StatsRunning = False
        self.TotalRequests = 0
        self.LastTickRequests = 0
        self.StartTime = None
        self.ActiveConnections = 0
        self.StatusCounts = {}
        self.StatsLock = threading.Lock()

    def IncrRequest(self, StatusCode):
        with self.StatsLock:
            self.TotalRequests += 1
            self.StatusCounts[StatusCode] = self.StatusCounts.get(StatusCode, 0) + 1

    def IncrActiveConnections(self):
        with self.StatsLock:
            self.ActiveConnections += 1

    def DecrActiveConnections(self):
        with self.StatsLock:
            self.ActiveConnections = max(0, self.ActiveConnections - 1)

    def StartStatsTicker(self):
        if self.Silent:
            return
        self.StartTime = time.time()
        self.StatsRunning = True
        self.StatsTicker = threading.Thread(
            target=self.TickerLoop, daemon=True, name="HellcatStatsTicker"
        )
        self.StatsTicker.start()

    def StopStatsTicker(self):
        self.StatsRunning = False

    def FormatUptime(self, Seconds):
        Seconds = int(Seconds)
        if Seconds < 60:
            return f"{Seconds}s"
        elif Seconds < 3600:
            return f"{Seconds // 60}m {Seconds % 60}s"
        else:
            H = Seconds // 3600
            M = (Seconds % 3600) // 60
            S = Seconds % 60
            return f"{H}h {M}m {S}s"

    def TickerLoop(self):
        TickInterval = 1.0

        while self.StatsRunning:
            time.sleep(TickInterval)
            if not self.StatsRunning:
                break

            with self.StatsLock:
                Total = self.TotalRequests
                Rps = Total - self.LastTickRequests
                self.LastTickRequests = Total
                Active = self.ActiveConnections
                StatusSnapshot = dict(self.StatusCounts)

            Uptime = (
                self.FormatUptime(time.time() - self.StartTime)
                if self.StartTime
                else "0s"
            )
            Ts = time.strftime("%H:%M:%S")

            def CodeColor(Code):
                if Code < 300:
                    return self.Green
                if Code < 400:
                    return self.Cyan
                if Code < 500:
                    return self.Yellow
                return self.Red

            StatusParts = []
            for Code in sorted(StatusSnapshot.keys()):
                Count = StatusSnapshot[Code]
                if Count > 0:
                    C = CodeColor(Code)
                    StatusParts.append(
                        f"{C}{self.Bold}{Code}{self.Reset}{self.Gray}:{self.Reset}{self.White}{Count}{self.Reset}"
                    )

            StatusStr = (
                ("  ".join(StatusParts))
                if StatusParts
                else f"{self.Gray}no requests{self.Reset}"
            )

            RpsColor = (
                self.Green if Rps < 50 else (self.Yellow if Rps < 200 else self.Red)
            )
            ActiveColor = self.Cyan if Active > 0 else self.Gray

            Line = (
                f"{self.White}{self.Bold}[{self.Reset}"
                f"{self.Cyan}{self.Bold}STATS{self.Reset}"
                f"{self.White}{self.Bold}]{self.Reset} "
                f"{self.Gray}{Ts}{self.Reset}  "
                f"up {self.White}{self.Bold}{Uptime}{self.Reset}  "
                f"req/s {RpsColor}{self.Bold}{Rps:>4}{self.Reset}  "
                f"total {self.White}{self.Bold}{Total}{self.Reset}  "
                f"active {ActiveColor}{self.Bold}{Active}{self.Reset}  "
                f"{StatusStr}"
            )

            with self.Lock:
                print(Line, flush=True)

    def Badge(self, Level, BracketColor, LevelColor):
        return f"{BracketColor}{self.Bold}[{self.Reset}{LevelColor}{self.Bold}{Level}{self.Reset}{BracketColor}{self.Bold}]{self.Reset}"

    def Timestamp(self):
        return time.strftime("%H:%M:%S")

    def Write(self, Level, Message, LevelColor, File=sys.stdout):
        Badge = self.Badge(Level, self.White, LevelColor)
        Ts = self.Timestamp()
        with self.Lock:
            print(
                f"{Badge} {self.Gray}{Ts}{self.Reset}  {Message}", file=File, flush=True
            )

    def Debug(self, Message):
        if not self.EnableDebug:
            return
        self.Write("DEBUG", f"{self.Gray}{Message}{self.Reset}", self.Yellow)

    def Info(self, Message):
        self.Write("INFO", f"{self.White}{Message}{self.Reset}", self.Green)

    def Warn(self, Message):
        self.Write(
            "WARN", f"{self.Yellow}{Message}{self.Reset}", self.Yellow, File=sys.stderr
        )

    def Error(self, Message):
        self.Write(
            "ERROR", f"{self.Red}{Message}{self.Reset}", self.Red, File=sys.stderr
        )

    def Sanitize(self, Text, MaxLen=60):
        Cleaned = "".join(
            Ch if (Ch.isprintable() and Ch not in "\r\n\t\x00") else "?"
            for Ch in str(Text)
        )
        return Cleaned[:MaxLen] + ("…" if len(Cleaned) > MaxLen else "")

    def Request(self, RemoteAddr, Method, Path, StatusCode, Duration):
        Method = self.Sanitize(Method, 10)
        Path = self.Sanitize(Path, 80)

        if StatusCode < 300:
            StatusColor = self.Green
        elif StatusCode < 400:
            StatusColor = self.Cyan
        elif StatusCode < 500:
            StatusColor = self.Yellow
        else:
            StatusColor = self.Red

        if Duration < 100:
            DurColor = self.Green
        elif Duration < 500:
            DurColor = self.Yellow
        else:
            DurColor = self.Red

        MethodColor = self.MethodColors.get(Method.upper(), self.Cyan)
        Ts = self.Timestamp()
        Badge = self.Badge("REQ", self.White, self.Blue)
        with self.Lock:
            print(
                f"{Badge} {self.Gray}{Ts}{self.Reset} {self.Gray}{RemoteAddr}{self.Reset} {MethodColor}{self.Bold}{Method}{self.Reset} {StatusColor}{self.Bold}{StatusCode}{self.Reset}  {self.White}{Path}{self.Reset} {DurColor}{Duration:.1f}ms{self.Reset}",
                flush=True,
            )
        self.IncrRequest(StatusCode)

    def TerminalWidth(self):
        try:
            import shutil

            W = shutil.get_terminal_size(fallback=(72, 24)).columns
            return max(40, min(W, 200))
        except Exception:
            return 72

    def StripAnsi(self, Text):
        import re

        return re.sub(r"\033\[[0-9;]*m", "", Text)

    def PrintRow(self, Label, Value, Vc, W):
        LabelCol = 18
        Content = f"{self.Gray}{Label:<{LabelCol}}{self.Reset}{Vc}{self.Bold}{Value}{self.Reset}"
        with self.Lock:
            print(Content, flush=True)

    def Banner(
        self,
        Protocol,
        Host,
        Port,
        Workers,
        RouteCount,
        AsyncMode=False,
        Routes=None,
        HttpRedirectPort=None,
    ):
        W = self.TerminalWidth()
        Thick = f"{self.Cyan}{'═' * W}{self.Reset}"
        Thin = f"{self.Gray}{'─' * W}{self.Reset}"

        with self.Lock:
            print("", flush=True)
            print(Thick, flush=True)
            print(
                f"{self.Cyan}{self.Bold}HellcatAPI  {self.Reset}{self.Gray}v{Version}{self.Reset}",
                flush=True,
            )
            print(Thin, flush=True)

        self.PrintRow("Host", f"{Protocol}://{Host}:{Port}", self.Green, W)
        self.PrintRow("Workers", str(Workers), self.White, W)
        self.PrintRow("Routes", str(RouteCount), self.White, W)
        self.PrintRow(
            "Async Mode",
            "enabled" if AsyncMode else "disabled",
            self.Green if AsyncMode else self.Gray,
            W,
        )
        self.PrintRow(
            "Debug Mode",
            "on" if self.EnableDebug else "off",
            self.Yellow if self.EnableDebug else self.Gray,
            W,
        )

        if HttpRedirectPort:
            self.PrintRow(
                "HTTP Redirect", f":{HttpRedirectPort} → :{Port}", self.Cyan, W
            )

        if Routes:
            MethodStrs = []
            TypeStrs = []
            PathStrs = []

            for Route in Routes:
                M = " | ".join(Route.Methods) if Route.Methods != ["*"] else "ANY"
                T = "async" if getattr(Route, "IsAsync", False) else "sync"
                MethodStrs.append(M)
                TypeStrs.append(T)
                PathStrs.append(Route.Pattern)

            ColM = max(len("Method"), max(len(M) for M in MethodStrs)) + 2
            ColT = max(len("Type"), max(len(T) for T in TypeStrs)) + 2
            ColP = max(len("Path"), W - ColM - ColT)

            with self.Lock:
                print(Thin, flush=True)
                Header = (
                    f"{self.Gray}{self.Bold}"
                    f"{'Method':<{ColM}}"
                    f"{'Type':<{ColT}}"
                    f"{'Path':<{ColP}}"
                    f"{self.Reset}"
                )
                print(Header, flush=True)
                print(f"{self.Gray}{'─' * W}{self.Reset}", flush=True)

            for M, T, P in zip(MethodStrs, TypeStrs, PathStrs):
                FirstMethod = M.split(" | ")[0].strip()
                Mc = self.MethodColors.get(FirstMethod.upper(), self.Purple)
                Tc = self.Cyan if T == "async" else self.Gray
                MaxPath = ColP - 1
                PDisplay = P if len(P) <= MaxPath else P[: MaxPath - 1] + "…"
                with self.Lock:
                    print(
                        f"{Mc}{self.Bold}{M:<{ColM}}{self.Reset}"
                        f"{Tc}{T:<{ColT}}{self.Reset}"
                        f"{self.White}{PDisplay}{self.Reset}",
                        flush=True,
                    )

        with self.Lock:
            print(Thick, flush=True)
            print("", flush=True)

    def Shutdown(self):
        self.Info("Server stopped.")


class HellcatConnectionHandler:
    def __init__(self, ClientSocket, RemoteAddress, Router, Logger, IsSslMode=False):
        self.ClientSocket = ClientSocket
        self.RemoteAddress = RemoteAddress
        self.Router = Router
        self.Logger = Logger
        self.IsSslMode = IsSslMode

    def SendPlainHttpToHttpsHint(self):
        try:
            Body = "This server requires HTTPS. Please use https:// instead of http://"
            Response = (
                f"HTTP/1.1 426 Upgrade Required\r\n"
                f"Upgrade: TLS/1.2\r\n"
                f"Connection: close\r\n"
                f"Content-Type: text/plain\r\n"
                f"Content-Length: {len(Body)}\r\n"
                f"\r\n"
                f"{Body}"
            )
            self.ClientSocket.sendall(Response.encode("utf-8"))
        except Exception:
            pass

    def IsTlsHandshake(self, RawData):
        return len(RawData) > 0 and RawData[0] == 0x16

    def IsHttpRequest(self, RawData):
        ValidMethods = (
            b"GET ",
            b"POST",
            b"PUT ",
            b"DELE",
            b"PATC",
            b"HEAD",
            b"OPTI",
            b"TRAC",
            b"CONN",
            b"QUER",
        )
        return any(RawData[:4].startswith(M[:4]) for M in ValidMethods)

    def Handle(self):
        self.Logger.IncrActiveConnections()
        try:
            self.ClientSocket.settimeout(KeepAliveTimeout)

            while True:
                RawData = self.ReadRequest()
                if not RawData:
                    break

                if not self.IsSslMode and self.IsTlsHandshake(RawData):
                    self.Logger.Debug(
                        f"TLS probe on HTTP port rejected: {self.RemoteAddress[0]}"
                    )
                    break

                if not self.IsSslMode and not self.IsHttpRequest(RawData):
                    self.Logger.Debug(
                        f"Non-HTTP data rejected: {self.RemoteAddress[0]}"
                    )
                    break

                self.ClientSocket.settimeout(SocketTimeout)

                try:
                    Request = HellcatRequestParser.Parse(RawData, self.RemoteAddress)
                except Exception as ParseErr:
                    self.Logger.Warn(
                        f"Parse error from {self.RemoteAddress[0]}: {ParseErr}"
                    )
                    break

                RequestContext.Clear()
                StartTime = time.time()
                Response = self.Dispatch(Request)

                ConnectionHeader = Request.Headers.get("connection", "").lower()
                ShouldClose = (
                    ConnectionHeader == "close" or Request.HttpVersion == "HTTP/1.0"
                )
                KeepAlive = not ShouldClose

                self.SendResponse(Response, KeepAlive=KeepAlive)
                Duration = (time.time() - StartTime) * 1000
                self.Logger.Request(
                    RemoteAddr=self.RemoteAddress[0],
                    Method=Request.Method,
                    Path=Request.Path,
                    StatusCode=Response.StatusCode,
                    Duration=Duration,
                )

                if ShouldClose:
                    break

                self.ClientSocket.settimeout(KeepAliveTimeout)

        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as Err:
            if "HellcatRequestParseError" not in type(Err).__name__:
                self.Logger.Error(
                    f"Unhandled error {self.RemoteAddress[0]}: {Err}\n{traceback.format_exc()}"
                )
        finally:
            self.Logger.DecrActiveConnections()
            try:
                self.ClientSocket.close()
            except OSError:
                pass

    def ReadRequest(self):
        Buffer = b""
        HeaderDone = False
        ContentLength = 0

        while True:
            try:
                Chunk = self.ClientSocket.recv(ReadChunkSize)
            except socket.timeout:
                break
            except OSError:
                break

            if not Chunk:
                break

            Buffer += Chunk

            if not HeaderDone and b"\r\n\r\n" in Buffer:
                HeaderDone = True
                HeaderEnd = Buffer.index(b"\r\n\r\n") + 4
                HeaderText = Buffer[:HeaderEnd].decode("utf-8", errors="replace")
                for Line in HeaderText.split("\r\n"):
                    if Line.lower().startswith("content-length:"):
                        try:
                            ContentLength = int(Line.split(":", 1)[1].strip())
                        except (ValueError, IndexError):
                            ContentLength = 0
                        break

            if HeaderDone:
                HeaderEnd = Buffer.index(b"\r\n\r\n") + 4
                BodyReceived = len(Buffer) - HeaderEnd
                if BodyReceived >= ContentLength:
                    break

            if len(Buffer) > MaxRequestSize:
                self.Logger.Warn(f"Request too large from {self.RemoteAddress[0]}")
                break

        return Buffer

    def Dispatch(self, Request):
        try:
            StaticMount = self.Router.GetStaticMount()
            if StaticMount and Request.Path.startswith(StaticMount["UrlPrefix"]):
                return self.ServeStatic(Request, StaticMount)

            Route, PathParams = self.Router.Resolve(Request)

            if Route is None:
                Handler = self.Router.GetErrorHandler(404)
                if Handler:
                    return Handler(Request, HellcatDispatchError("Route not found"))
                return HellcatErrorResponse("Route not found", StatusCode=404)

            if not Route.AllowsMethod(Request.Method):
                Handler = self.Router.GetErrorHandler(405)
                if Handler:
                    return Handler(Request, HellcatDispatchError("Method not allowed"))
                return HellcatErrorResponse(
                    f"Method '{Request.Method}' not allowed", StatusCode=405
                )

            Request.PathParams = PathParams
            GlobalMiddlewares = self.Router.GetGlobalMiddlewares()
            AllMiddlewares = GlobalMiddlewares + Route.Middlewares

            return self.RunMiddlewarePipeline(Request, Route.Handler, AllMiddlewares)

        except Exception as Err:
            if "HellcatStaticFileError" in type(Err).__name__:
                return HellcatErrorResponse(str(Err), StatusCode=500)
            raise HellcatDispatchError(f"Dispatch error: {Err}")

    def RunMiddlewarePipeline(self, Request, FinalHandler, Middlewares):
        AsyncMode = getattr(self.Router, "AsyncMode", False)
        if AsyncMode or HasAnyAsync(Middlewares, FinalHandler):
            try:
                return RunAsyncPipeline(Request, FinalHandler, Middlewares)
            except Exception as Err:
                self.Logger.Error(
                    f"Async pipeline error: {Err}\n{traceback.format_exc()}"
                )
                Handler = self.Router.GetErrorHandler(500)
                if Handler:
                    return Handler(Request, Err)
                return HellcatErrorResponse("Async handler error", StatusCode=500)

        def BuildChain(Index):
            if Index >= len(Middlewares):
                return FinalHandler
            Current = Middlewares[Index]

            def Next(Req):
                return BuildChain(Index + 1)(Req)

            def Wrapper(Req):
                return Current(Req, Next)

            return Wrapper

        return self.SafeCall(BuildChain(0), Request)

    def SafeCall(self, Handler, Request):
        try:
            return CallHandler(Handler, Request)
        except Exception as Err:
            self.Logger.Error(f"Handler error: {Err}\n{traceback.format_exc()}")
            ErrorHandler = self.Router.GetErrorHandler(500)
            if ErrorHandler:
                return ErrorHandler(Request, Err)
            return HellcatErrorResponse("Internal server error", StatusCode=500)

    def ParseTupleResponse(self, TupleResult):
        def Make(Body, Status):
            if isinstance(Body, dict):
                return HellcatJsonResponse(Body, StatusCode=Status)
            if isinstance(Body, str):
                return HellcatHtmlResponse(Body, StatusCode=Status)
            return HellcatResponse(Body=Body, StatusCode=Status)

        if len(TupleResult) == 2:
            return Make(TupleResult[0], TupleResult[1])
        if len(TupleResult) == 3:
            Body, Status, Headers = TupleResult
            Resp = Make(Body, Status)
            if isinstance(Headers, dict):
                for K, V in Headers.items():
                    Resp.SetHeader(K, V)
            return Resp
        return HellcatErrorResponse("Invalid response tuple", StatusCode=500)

    def ServeStatic(self, Request, StaticMount):
        UrlPrefix = StaticMount["UrlPrefix"]
        DirectoryPath = StaticMount["DirectoryPath"]
        RelativePath = Request.Path[len(UrlPrefix) :].lstrip("/")
        FilePath = os.path.normpath(os.path.join(DirectoryPath, RelativePath))
        RootPath = os.path.normpath(DirectoryPath)

        if not FilePath.startswith(RootPath):
            self.Logger.Warn(
                f"Traversal attempt from {self.RemoteAddress[0]}: {Request.Path}"
            )
            return HellcatErrorResponse("Access denied", StatusCode=403)

        if os.path.isdir(FilePath):
            FilePath = os.path.join(FilePath, "index.html")

        if not os.path.isfile(FilePath):
            return HellcatErrorResponse(
                f"Static file not found: {Request.Path}", StatusCode=404
            )

        try:
            return HellcatFileResponse(FilePath)
        except OSError as Err:
            raise HellcatStaticFileError(f"Cannot read static file '{FilePath}': {Err}")

    def SendResponse(self, Response, KeepAlive=False):
        if isinstance(Response, HellcatStreamResponse):
            self.SendStreamResponse(Response)
            return
        try:
            self.ClientSocket.sendall(Response.Build(KeepAlive=KeepAlive))
        except BrokenPipeError:
            self.Logger.Debug(f"Broken pipe: {self.RemoteAddress[0]}")
        except ConnectionResetError:
            self.Logger.Debug(f"Reset sending: {self.RemoteAddress[0]}")
        except OSError as Err:
            raise HellcatResponseBuildError(
                f"Send failed to {self.RemoteAddress[0]}: {Err}"
            )

    def SendStreamResponse(self, Response):
        try:
            self.ClientSocket.sendall(Response.BuildHeader())
            for Chunk in Response.GeneratorFunc():
                if isinstance(Chunk, str):
                    Chunk = Chunk.encode("utf-8")
                if not Chunk:
                    continue
                ChunkSize = f"{len(Chunk):x}\r\n".encode("utf-8")
                self.ClientSocket.sendall(ChunkSize + Chunk + b"\r\n")
            self.ClientSocket.sendall(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            self.Logger.Debug(f"Stream closed: {self.RemoteAddress[0]}")
        except OSError as Err:
            self.Logger.Warn(f"Stream OS error {self.RemoteAddress[0]}: {Err}")
        except Exception as Err:
            self.Logger.Error(
                f"Stream error {self.RemoteAddress[0]}: {Err}\n{traceback.format_exc()}"
            )


class HellcatServer:
    def __init__(
        self,
        Router,
        Host=DefaultHost,
        Port=DefaultPort,
        Workers=None,
        SslCertFile=None,
        SslKeyFile=None,
        HttpRedirectPort=None,
        Silent=False,
        EnableDebug=False,
        SocketBacklog=512,
        Logger=None,
        Asynchronous=False,
    ):
        self.Router = Router
        self.Host = Host
        self.Port = Port
        self.Workers = Workers or (os.cpu_count() or 4) * 4
        self.SslCertFile = SslCertFile
        self.SslKeyFile = SslKeyFile
        self.HttpRedirectPort = HttpRedirectPort
        self.SocketBacklog = SocketBacklog
        self.Asynchronous = Asynchronous
        self.Logger = (
            Logger
            if Logger is not None
            else HellcatLogger(Silent=Silent, EnableDebug=EnableDebug)
        )
        self.IsRunning = False
        self.ServerSocket = None
        self.RedirectSocket = None
        self.SslCtx = None
        self.ThreadPool = None
        self.RequestCount = 0
        self.ErrorCount = 0
        self.StartTime = None
        self.CounterLock = threading.Lock()
        self.BindHost = None

    def CreateSocket(self):
        self.BindHost = self.ResolveBindAddress(self.Host)
        try:
            Sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            Sock.bind((self.BindHost, self.Port))
            Sock.listen(self.SocketBacklog)
            return Sock
        except OSError as Err:
            raise HellcatSocketError(
                f"Cannot bind to {self.BindHost}:{self.Port}\n"
                f"  Requested Host : {self.Host}\n"
                f"  Resolved to    : {self.BindHost}\n"
                f"  Tip: Use '0.0.0.0' to listen on all interfaces, or your device's local IP.\n"
                f"  Cause: {Err}"
            )

    def ResolveBindAddress(self, Host):
        if Host in ("0.0.0.0", "127.0.0.1", "localhost", "::"):
            return Host
        try:
            socket.inet_aton(Host)
            return Host
        except socket.error:
            pass
        self.Logger.Warn(
            f"Host '{Host}' looks like a domain name, not a bind address. "
            f"Falling back to 0.0.0.0 — the server will listen on all interfaces. "
            f"Use your domain only in DNS/reverse proxy, not in App.Run(Host=...)."
        )
        return "0.0.0.0"

    def CreateSslContext(self):
        if not self.SslCertFile or not self.SslKeyFile:
            raise HellcatSslError("SSL requires both SslCertFile and SslKeyFile")
        if not os.path.isfile(self.SslCertFile):
            raise HellcatSslError(f"Cert file not found: '{self.SslCertFile}'")
        if not os.path.isfile(self.SslKeyFile):
            raise HellcatSslError(f"Key file not found: '{self.SslKeyFile}'")
        try:
            Ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            Ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            Ctx.load_cert_chain(self.SslCertFile, self.SslKeyFile)
            return Ctx
        except ssl.SSLError as Err:
            raise HellcatSslError(f"SSL init failed: {Err}")

    def StartHttpRedirectLoop(self, RedirectPort, HttpsPort, BindHost):
        try:
            Sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            Sock.bind((BindHost, RedirectPort))
            Sock.listen(128)
            self.RedirectSocket = Sock
            self.Logger.Info(f"HTTP→HTTPS redirect active on port {RedirectPort}")
        except OSError as Err:
            self.Logger.Warn(
                f"Cannot start HTTP redirect on port {RedirectPort}: {Err}"
            )
            return

        def RedirectLoop():
            while self.IsRunning:
                try:
                    Conn, Addr = Sock.accept()
                    self.ThreadPool.submit(
                        self.HandleHttpRedirect, Conn, Addr, HttpsPort
                    )
                except OSError:
                    break

        T = threading.Thread(
            target=RedirectLoop, daemon=True, name="HellcatHttpRedirect"
        )
        T.start()

    def HandleHttpRedirect(self, Conn, Addr, HttpsPort):
        try:
            Conn.settimeout(5)
            Raw = Conn.recv(4096)
            if not Raw:
                return
            Host = "localhost"
            Path = "/"
            for Line in Raw.decode("utf-8", errors="replace").split("\r\n"):
                if Line.lower().startswith("host:"):
                    Host = Line.split(":", 1)[1].strip().split(":")[0]
                if (
                    Line.startswith("GET ")
                    or Line.startswith("POST ")
                    or Line.startswith("HEAD ")
                ):
                    Parts = Line.split(" ")
                    if len(Parts) >= 2:
                        Path = Parts[1]
            Location = (
                f"https://{Host}:{HttpsPort}{Path}"
                if HttpsPort != 443
                else f"https://{Host}{Path}"
            )
            Body = f"Redirecting to {Location}"
            Response = (
                f"HTTP/1.1 301 Moved Permanently\r\n"
                f"Location: {Location}\r\n"
                f"Content-Length: {len(Body)}\r\n"
                f"Content-Type: text/plain\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"{Body}"
            )
            Conn.sendall(Response.encode("utf-8"))
            self.Logger.Debug(f"HTTP→HTTPS redirect: {Addr[0]} → {Location}")
        except Exception:
            pass
        finally:
            try:
                Conn.close()
            except OSError:
                pass

    def AcceptLoop(self):
        self.Router.AsyncMode = self.Asynchronous
        while self.IsRunning:
            try:
                ClientSocket, RemoteAddress = self.ServerSocket.accept()
                with self.CounterLock:
                    self.RequestCount += 1

                if self.SslCtx is not None:
                    try:
                        ClientSocket = self.SslCtx.wrap_socket(
                            ClientSocket, server_side=True
                        )
                    except ssl.SSLError as Err:
                        self.Logger.Debug(
                            f"SSL handshake failed from {RemoteAddress[0]}: {Err}"
                        )
                        try:
                            ClientSocket.close()
                        except OSError:
                            pass
                        continue

                IsSsl = self.SslCtx is not None
                Handler = HellcatConnectionHandler(
                    ClientSocket=ClientSocket,
                    RemoteAddress=RemoteAddress,
                    Router=self.Router,
                    Logger=self.Logger,
                    IsSslMode=IsSsl,
                )
                self.ThreadPool.submit(Handler.Handle)
            except ssl.SSLError as Err:
                self.Logger.Debug(f"SSL handshake failed from unknown: {Err}")
            except OSError as Err:
                if self.IsRunning:
                    self.Logger.Error(f"Accept loop error: {Err}")
            except Exception as Err:
                if self.IsRunning:
                    self.Logger.Error(
                        f"Accept loop unhandled: {Err}\n{traceback.format_exc()}"
                    )

    def Start(self, Blocking=True):
        try:
            self.ServerSocket = self.CreateSocket()
        except HellcatSocketError as Err:
            self.Logger.Error(f"Cannot start server — socket error:\n  {Err}")
            raise

        try:
            if self.SslCertFile and self.SslKeyFile:
                self.SslCtx = self.CreateSslContext()
                Protocol = "https"
            else:
                self.SslCtx = None
                Protocol = "http"
        except HellcatSslError as Err:
            self.Logger.Error(f"Cannot start server — SSL error:\n  {Err}")
            try:
                self.ServerSocket.close()
            except Exception:
                pass
            raise

        try:
            self.ThreadPool = ThreadPoolExecutor(max_workers=self.Workers)
        except Exception as Err:
            self.Logger.Error(f"Cannot create thread pool: {Err}")
            raise HellcatServerError(f"Thread pool init failed: {Err}")

        self.IsRunning = True
        self.StartTime = time.time()

        AllRoutes = self.Router.ListRoutes()
        RouteCount = len(AllRoutes)
        self.Logger.Banner(
            Protocol,
            self.Host,
            self.Port,
            self.Workers,
            RouteCount,
            AsyncMode=self.Asynchronous,
            Routes=AllRoutes,
            HttpRedirectPort=self.HttpRedirectPort if Protocol == "https" else None,
        )

        self.Logger.StartStatsTicker()

        if Protocol == "https" and self.HttpRedirectPort:
            self.StartHttpRedirectLoop(self.HttpRedirectPort, self.Port, self.BindHost)

        AcceptThread = threading.Thread(
            target=self.AcceptLoop, daemon=True, name="HellcatAccept"
        )
        AcceptThread.start()

        if Blocking:
            try:
                while self.IsRunning:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.Logger.Info("Stopping server...")
                self.Stop()

    def Stop(self):
        self.IsRunning = False
        self.Logger.StopStatsTicker()
        for Sock in (self.ServerSocket, self.RedirectSocket):
            if Sock:
                try:
                    Sock.close()
                except OSError as Err:
                    self.Logger.Warn(f"Socket close error: {Err}")
        if self.ThreadPool:
            try:
                self.ThreadPool.shutdown(wait=False)
            except Exception as Err:
                self.Logger.Warn(f"ThreadPool shutdown error: {Err}")
        self.Logger.Shutdown()

    def GetStats(self):
        Uptime = round(time.time() - self.StartTime, 2) if self.StartTime else 0
        return {
            "Host": self.Host,
            "Port": self.Port,
            "Workers": self.Workers,
            "TotalRequests": self.RequestCount,
            "IsRunning": self.IsRunning,
            "Routes": len(self.Router.ListRoutes()),
            "Asynchronous": self.Asynchronous,
            "UptimeSeconds": Uptime,
        }

    def __repr__(self):
        return f"<HellcatServer {self.Host}:{self.Port} workers={self.Workers} running={self.IsRunning}>"
