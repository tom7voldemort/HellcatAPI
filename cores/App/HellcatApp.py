import os
import sys
import inspect

from cores.Router.HellcatRouter import HellcatRouter
from cores.Async.HellcatAsync import (
    CallWithTimeout,
    GatherSafe,
    IsCoroutineFunction,
    HellcatAsyncError,
    HellcatAsyncTimeoutError,
    HellcatCoroutineError,
    HellcatEventLoopError,
    HellcatAsyncMiddlewareError,
)
from cores.Server.HellcatServer import (
    HellcatServer,
    HellcatServerError,
    HellcatSocketError,
    HellcatSslError,
    HellcatLogger,
    DefaultHost,
    DefaultPort,
)
from cores.Template.HellcatTemplate import HellcatTemplateEngine, HellcatTemplateError
from cores.Context.HellcatContext import HellcatSessionStore, HellcatJwtUtil, RequestContext
from cores.Response.HellcatResponse import (
    HellcatResponse,
    HellcatJsonResponse,
    HellcatHtmlResponse,
    HellcatRedirectResponse,
    HellcatFileResponse,
    HellcatErrorResponse,
    HellcatStreamResponse,
)
from cores.Middleware.HellcatMiddleware import (
    HellcatCorsMiddleware,
    HellcatRateLimitMiddleware,
    HellcatSecurityHeadersMiddleware,
    HellcatGzipMiddleware,
    HellcatBasicAuthMiddleware,
    HellcatBearerAuthMiddleware,
    HellcatBodySizeLimitMiddleware,
    HellcatCsrfMiddleware,
    HellcatJsonValidatorMiddleware,
)


class HellcatAppError(Exception):
    """"""


class HellcatTemplateDirError(HellcatAppError):
    """"""


class HellcatStaticDirError(HellcatAppError):
    """"""


class HellcatPathResolverError(HellcatAppError):
    """"""


class HellcatPathResolver:
    """"""

    @staticmethod
    def FindCallerDirectory(StackDepth=3):
        try:
            Stack = inspect.stack()
            for Frame in Stack[StackDepth:]:
                CallerFile = Frame.filename
                if CallerFile and "<" not in CallerFile:
                    AbsPath = os.path.abspath(CallerFile)
                    return os.path.dirname(AbsPath)
        except Exception:
            pass
        return os.getcwd()

    @staticmethod
    def Resolve(PathInput, CallerDir, Label="path"):
        if PathInput is None:
            return None, False

        if os.path.isabs(PathInput):
            if os.path.isdir(PathInput):
                return PathInput, True
            return None, False

        CandidateFromCaller = os.path.join(CallerDir, PathInput)
        if os.path.isdir(CandidateFromCaller):
            return os.path.abspath(CandidateFromCaller), True

        CandidateFromCwd = os.path.join(os.getcwd(), PathInput)
        if os.path.isdir(CandidateFromCwd):
            return os.path.abspath(CandidateFromCwd), True

        return None, False

    @staticmethod
    def ResolveOrCreate(PathInput, CallerDir, Label="path", AutoCreate=False):
        ResolvedPath, Found = HellcatPathResolver.Resolve(PathInput, CallerDir, Label)
        if Found:
            return ResolvedPath, True

        if AutoCreate and PathInput is not None:
            TargetPath = (
                PathInput
                if os.path.isabs(PathInput)
                else os.path.join(CallerDir, PathInput)
            )
            try:
                os.makedirs(TargetPath, exist_ok=True)
                return os.path.abspath(TargetPath), True
            except OSError as Err:
                raise HellcatPathResolverError(
                    f"Could not auto-create {Label} directory '{TargetPath}': {Err}"
                ) from Err

        return None, False


class HellcatApp:
    """"""

    def __init__(
        self,
        TemplateDir="templates",
        StaticDir=None,
        StaticUrl="/static",
        SecretKey=None,
        AutoCreateDirs=False,
    ):
        self.Debug     = False
        self.SecretKey = SecretKey or "hellcat-secret-change-this-in-production"
        self.Router    = HellcatRouter()
        self.Sessions  = HellcatSessionStore()
        self.Server    = None
        self.Context   = RequestContext
        self.Logger    = HellcatLogger(EnableDebug=False)

        self.CallerDir = HellcatPathResolver.FindCallerDirectory(StackDepth=2)
        self.TemplateDirInput = TemplateDir
        self.StaticDirInput = StaticDir
        self.StaticUrl = StaticUrl

        self.ResolvedTemplateDir = None
        self.ResolvedStaticDir = None

        self.SetupTemplateEngine(TemplateDir, AutoCreateDirs)
        self.SetupStaticServing(StaticDir, StaticUrl, AutoCreateDirs)

    def SetupTemplateEngine(self, TemplateDir, AutoCreate):
        if TemplateDir is None:
            self.Templates = None
            return

        try:
            ResolvedPath, Found = HellcatPathResolver.ResolveOrCreate(
                TemplateDir, self.CallerDir, Label="TemplateDir", AutoCreate=AutoCreate
            )
        except HellcatPathResolverError as Err:
            self.WarnMissingDir("TemplateDir", TemplateDir, str(Err))
            self.Templates = None
            return

        if Found:
            self.ResolvedTemplateDir = ResolvedPath
            self.Templates = HellcatTemplateEngine(TemplateDirectory=ResolvedPath)
        else:
            ExpectedPath = os.path.join(self.CallerDir, TemplateDir)
            self.ResolvedTemplateDir = None
            self.Templates = None
            self.WarnMissingDir("TemplateDir", TemplateDir, ExpectedPath)

    def SetupStaticServing(self, StaticDir, StaticUrl, AutoCreate):
        if StaticDir is None:
            return

        try:
            ResolvedPath, Found = HellcatPathResolver.ResolveOrCreate(
                StaticDir, self.CallerDir, Label="StaticDir", AutoCreate=AutoCreate
            )
        except HellcatPathResolverError as Err:
            self.WarnMissingDir("StaticDir", StaticDir, str(Err))
            return

        if Found:
            self.ResolvedStaticDir = ResolvedPath
            self.Router.MountStatic(StaticUrl, ResolvedPath)
        else:
            ExpectedPath = os.path.join(self.CallerDir, StaticDir)
            self.ResolvedStaticDir = None
            self.WarnMissingDir("StaticDir", StaticDir, ExpectedPath)

    def WarnMissingDir(self, Label, InputPath, Detail):
        self.Logger.Warn(
            f"{Label} '{InputPath}' not found. "
            f"Detail: {Detail} | "
            f"Caller dir: {self.CallerDir} | "
            f"Tip: create the directory or pass AutoCreateDirs=True"
        )

    def SetTemplateDir(self, NewPath):
        ResolvedPath, Found = HellcatPathResolver.Resolve(
            NewPath, self.CallerDir, Label="TemplateDir"
        )
        if not Found:
            raise HellcatTemplateDirError(
                f"TemplateDir not found: '{NewPath}' "
                f"(searched relative to '{self.CallerDir}')"
            )
        self.ResolvedTemplateDir = ResolvedPath
        if self.Templates:
            self.Templates.TemplateDirectory = ResolvedPath
            self.Templates.ClearCache()
        else:
            self.Templates = HellcatTemplateEngine(TemplateDirectory=ResolvedPath)

    def SetStaticDir(self, NewPath, NewUrl=None):
        ResolvedPath, Found = HellcatPathResolver.Resolve(
            NewPath, self.CallerDir, Label="StaticDir"
        )
        if not Found:
            raise HellcatStaticDirError(
                f"StaticDir not found: '{NewPath}' "
                f"(searched relative to '{self.CallerDir}')"
            )
        self.ResolvedStaticDir = ResolvedPath
        UrlPrefix = NewUrl or self.StaticUrl
        self.Router.MountStatic(UrlPrefix, ResolvedPath)

    def GetPaths(self):
        return {
            "CallerDir": self.CallerDir,
            "TemplateDir": self.ResolvedTemplateDir,
            "StaticDir": self.ResolvedStaticDir,
            "StaticUrl": self.StaticUrl,
            "TemplateDirInput": self.TemplateDirInput,
            "StaticDirInput": self.StaticDirInput,
        }

    def Route(self, Path, Methods=None, Middlewares=None):
        return self.Router.Route(Path, Methods=Methods, Middlewares=Middlewares)

    def Get(self, Path, Middlewares=None):
        return self.Router.Get(Path, Middlewares=Middlewares)

    def Post(self, Path, Middlewares=None):
        return self.Router.Post(Path, Middlewares=Middlewares)

    def Put(self, Path, Middlewares=None):
        return self.Router.Put(Path, Middlewares=Middlewares)

    def Delete(self, Path, Middlewares=None):
        return self.Router.Delete(Path, Middlewares=Middlewares)

    def Patch(self, Path, Middlewares=None):
        return self.Router.Patch(Path, Middlewares=Middlewares)

    def Head(self, Path, Middlewares=None):
        return self.Router.Head(Path, Middlewares=Middlewares)

    def Options(self, Path, Middlewares=None):
        return self.Router.Options(Path, Middlewares=Middlewares)

    def Trace(self, Path, Middlewares=None):
        return self.Router.Trace(Path, Middlewares=Middlewares)

    def Any(self, Path, Middlewares=None):
        return self.Router.Any(Path, Middlewares=Middlewares)

    def ErrorHandler(self, StatusCode):
        return self.Router.ErrorHandler(StatusCode)

    def UseMiddleware(self, MiddlewareInstance):
        self.Router.AddMiddleware(MiddlewareInstance)

    def UseCors(self, AllowedOrigins=None, AllowCredentials=False):
        self.UseMiddleware(
            HellcatCorsMiddleware(
                AllowedOrigins=AllowedOrigins or ["*"],
                AllowCredentials=AllowCredentials,
            )
        )

    def UseRateLimit(self, MaxRequests=100, WindowSeconds=60):
        self.UseMiddleware(
            HellcatRateLimitMiddleware(
                MaxRequests=MaxRequests, WindowSeconds=WindowSeconds
            )
        )

    def UseSecurityHeaders(self):
        self.UseMiddleware(HellcatSecurityHeadersMiddleware())

    def UseGzip(self, MinSizeBytes=1024):
        self.UseMiddleware(HellcatGzipMiddleware(MinSizeBytes=MinSizeBytes))

    def UseBodySizeLimit(self, MaxBytes=10 * 1024 * 1024):
        self.UseMiddleware(HellcatBodySizeLimitMiddleware(MaxBytes=MaxBytes))

    def Include(self, SubRouter):
        self.Router.Include(SubRouter)

    def Json(self, Data, StatusCode=200):
        return HellcatJsonResponse(Data, StatusCode=StatusCode)

    def Html(self, HtmlContent, StatusCode=200):
        return HellcatHtmlResponse(HtmlContent, StatusCode=StatusCode)

    def Text(self, Content, StatusCode=200):
        return HellcatResponse(
            Body=Content, StatusCode=StatusCode, ContentType="text/plain; charset=utf-8"
        )

    def Redirect(self, Location, StatusCode=302):
        return HellcatRedirectResponse(Location=Location, StatusCode=StatusCode)

    def File(self, FilePath, DownloadAs=None):
        if os.path.isabs(FilePath):
            if not os.path.isfile(FilePath):
                return HellcatErrorResponse(
                    f"File not found: '{FilePath}'", StatusCode=404
                )
            return HellcatFileResponse(FilePath=FilePath, DownloadAs=DownloadAs)

        Candidates = []

        if self.ResolvedStaticDir:
            Candidates.append(os.path.join(self.ResolvedStaticDir, FilePath))

        if self.CallerDir:
            Candidates.append(os.path.join(self.CallerDir, FilePath))

        Candidates.append(os.path.join(os.getcwd(), FilePath))

        for Candidate in Candidates:
            NormalizedPath = os.path.normpath(Candidate)
            if os.path.isfile(NormalizedPath):
                return HellcatFileResponse(
                    FilePath=NormalizedPath, DownloadAs=DownloadAs
                )

        return HellcatErrorResponse(
            f"File '{FilePath}' not found. Searched in: {', '.join(Candidates)}",
            StatusCode=404,
        )

    def Error(self, Message, StatusCode=400, Details=None):
        return HellcatErrorResponse(
            Message=Message, StatusCode=StatusCode, Details=Details
        )

    def Stream(self, GeneratorFunc, ContentType="text/event-stream"):
        return HellcatStreamResponse(
            GeneratorFunc=GeneratorFunc, ContentType=ContentType
        )

    def Render(self, TemplateName, Context=None):
        if self.Templates is None:
            return HellcatErrorResponse(
                f"Template engine is not active. "
                f"Directory '{self.TemplateDirInput}' was not found at startup "
                f"(caller dir: '{self.CallerDir}'). "
                f"Create the directory or pass AutoCreateDirs=True.",
                StatusCode=500,
            )

        try:
            HtmlContent = self.Templates.Render(TemplateName, Context or {})
            return HellcatHtmlResponse(HtmlContent)

        except HellcatTemplateError as Err:
            ErrorMessage = str(Err)
            if any(
                Phrase in ErrorMessage.lower()
                for Phrase in ("not found", "tidak ditemukan")
            ):
                return HellcatErrorResponse(
                    f"Template '{TemplateName}' not found "
                    f"in '{self.ResolvedTemplateDir}'.",
                    StatusCode=404,
                )
            if self.Debug:
                return HellcatErrorResponse(
                    f"Template render error: {ErrorMessage}", StatusCode=500
                )
            return HellcatErrorResponse("Failed to render template.", StatusCode=500)

        except Exception as Err:
            if self.Debug:
                return HellcatErrorResponse(
                    f"Unexpected template error: {Err}", StatusCode=500
                )
            return HellcatErrorResponse("Internal server error.", StatusCode=500)

    def RenderString(self, TemplateString, Context=None):
        try:
            Engine = self.Templates or HellcatTemplateEngine(TemplateDirectory="")
            HtmlContent = Engine.RenderString(TemplateString, Context or {})
            return HellcatHtmlResponse(HtmlContent)

        except HellcatTemplateError as Err:
            if self.Debug:
                return HellcatErrorResponse(
                    f"Template render error: {Err}", StatusCode=500
                )
            return HellcatErrorResponse(
                "Failed to render template string.", StatusCode=500
            )

        except Exception as Err:
            if self.Debug:
                return HellcatErrorResponse(
                    f"Unexpected error rendering template string: {Err}", StatusCode=500
                )
            return HellcatErrorResponse("Internal server error.", StatusCode=500)

    def GetSession(self, Request):
        SessionId = Request.Cookies.get("hellcat_session")
        if not SessionId:
            return {}, None
        Data = self.Sessions.Get(SessionId)
        return Data, SessionId

    def SaveSession(self, Response, SessionData, SessionId=None):
        if not SessionId:
            SessionId = self.Sessions.GenerateSessionId()
            Response.SetCookie("hellcat_session", SessionId, HttpOnly=True)
        self.Sessions.Set(SessionId, SessionData)
        return SessionId

    def CreateJwt(self, Payload, ExpiresIn=3600):
        return HellcatJwtUtil.Encode(Payload, self.SecretKey, ExpiresIn=ExpiresIn)

    def DecodeJwt(self, Token):
        return HellcatJwtUtil.Decode(Token, self.SecretKey)

    async def AsyncRender(self, TemplateName, Context=None):
        return self.Render(TemplateName, Context)

    async def AsyncJson(self, Data, StatusCode=200):
        return self.Json(Data, StatusCode)

    async def AsyncError(self, Message, StatusCode=400, Details=None):
        return self.Error(Message, StatusCode, Details)

    async def Gather(self, *Coroutines):
        return await GatherSafe(*Coroutines)

    async def Timeout(self, Coro, Seconds):
        return await CallWithTimeout(Coro, Seconds)

    def Run(
        self,
        Host=DefaultHost,
        Port=DefaultPort,
        Workers=None,
        SslCertFile=None,
        SslKeyFile=None,
        HttpRedirectPort=None,
        Blocking=True,
        Debug=False,
        Asynchronous=False,
        Logger=True,
    ):
        self.Debug                = Debug
        self.Logger.EnableDebug   = Debug
        self.Logger.Silent        = not Logger

        self.Server = HellcatServer(
            Router=self.Router,
            Host=Host,
            Port=Port,
            Workers=Workers,
            SslCertFile=SslCertFile,
            SslKeyFile=SslKeyFile,
            HttpRedirectPort=HttpRedirectPort,
            Silent=False,
            EnableDebug=Debug,
            Logger=self.Logger,
            Asynchronous=Asynchronous,
        )
        try:
            self.Server.Start(Blocking=Blocking)
        except HellcatSslError:
            sys.exit(1)
        except HellcatSocketError:
            sys.exit(1)
        except HellcatServerError:
            sys.exit(1)
        except KeyboardInterrupt:
            pass

    def Stop(self):
        if self.Server:
            self.Server.Stop()

    def GetStats(self):
        if self.Server:
            return self.Server.GetStats()
        return {}

    def ListRoutes(self):
        return self.Router.ListRoutes()

    def __repr__(self):
        RouteCount = len(self.Router.ListRoutes())
        return f"<HellcatApp routes={RouteCount} debug={self.Debug}>"
