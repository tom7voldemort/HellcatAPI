import re
import os
import functools
import asyncio


class HellcatRouterError(Exception):
    """"""


class HellcatPatternCompileError(HellcatRouterError):
    """"""


class HellcatDuplicateRouteError(HellcatRouterError):
    """"""


class HellcatRoute:
    """"""

    def __init__(self, Pattern, Handler, Methods, Middlewares=None):
        self.Pattern = Pattern
        self.Handler = Handler
        self.Methods = [M.upper() for M in Methods]
        self.Middlewares = Middlewares or []

        try:
            self.Regex, self.ParamNames = HellcatRoute.CompilePattern(Pattern)
        except re.error as Err:
            raise HellcatPatternCompileError(
                f"Invalid URL pattern '{Pattern}': {Err}"
            ) from Err

    @staticmethod
    def CompilePattern(Pattern):
        ParamNames = []
        RegexPattern = "^"
        Segments = Pattern.split("/")

        for Segment in Segments:
            if not Segment:
                continue
            RegexPattern += "/"

            if Segment.startswith("<int:") and Segment.endswith(">"):
                ParamName = Segment[5:-1]
                if not ParamName.isidentifier():
                    raise HellcatPatternCompileError(
                        f"Invalid parameter name '{ParamName}' in pattern '{Pattern}'"
                    )
                ParamNames.append(ParamName)
                RegexPattern += f"(?P<{ParamName}>[0-9]+)"

            elif Segment.startswith("<") and Segment.endswith(">"):
                ParamName = Segment[1:-1]
                if not ParamName.isidentifier():
                    raise HellcatPatternCompileError(
                        f"Invalid parameter name '{ParamName}' in pattern '{Pattern}'"
                    )
                ParamNames.append(ParamName)
                RegexPattern += f"(?P<{ParamName}>[^/]+)"

            else:
                RegexPattern += re.escape(Segment)

        RegexPattern += "/?$"
        return re.compile(RegexPattern), ParamNames

    def Match(self, Path):
        Result = self.Regex.match(Path)
        if Result:
            return Result.groupdict()
        return None

    def AllowsMethod(self, Method):
        return Method.upper() in self.Methods or "*" in self.Methods

    def __repr__(self):
        return f"<HellcatRoute {self.Methods} {self.Pattern}>"


class HellcatRouter:
    """"""

    def __init__(self, Prefix=""):
        self.Prefix = Prefix.rstrip("/")
        self.Routes = []
        self.GlobalMiddlewares = []
        self.ErrorHandlers = {}
        self.StaticMount = None
        self.AsyncMode = False

    def NormalizePath(self, Path):
        FullPath = self.Prefix + "/" + Path.lstrip("/")
        return FullPath.rstrip("/") or "/"

    def Route(self, Path, Methods=None, Middlewares=None):
        if Methods is None:
            Methods = ["GET"]

        def Decorator(HandlerFunc):
            FullPath = self.NormalizePath(Path)
            try:
                NewRoute = HellcatRoute(
                    Pattern=FullPath,
                    Handler=HandlerFunc,
                    Methods=Methods,
                    Middlewares=Middlewares or [],
                )
            except HellcatPatternCompileError:
                raise

            NewRoute.IsAsync = asyncio.iscoroutinefunction(HandlerFunc)
            self.Routes.append(NewRoute)

            if asyncio.iscoroutinefunction(HandlerFunc):
                @functools.wraps(HandlerFunc)
                async def Wrapper(*Args, **Kwargs):
                    return await HandlerFunc(*Args, **Kwargs)
            else:
                @functools.wraps(HandlerFunc)
                def Wrapper(*Args, **Kwargs):
                    return HandlerFunc(*Args, **Kwargs)

            return Wrapper

        return Decorator

    def Get(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["GET"], Middlewares=Middlewares)

    def Post(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["POST"], Middlewares=Middlewares)

    def Put(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["PUT"], Middlewares=Middlewares)

    def Delete(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["DELETE"], Middlewares=Middlewares)

    def Patch(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["PATCH"], Middlewares=Middlewares)

    def Head(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["HEAD"], Middlewares=Middlewares)

    def Options(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["OPTIONS"], Middlewares=Middlewares)

    def Trace(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["TRACE"], Middlewares=Middlewares)

    def Any(self, Path, Middlewares=None):
        return self.Route(Path, Methods=["*"], Middlewares=Middlewares)

    def AddMiddleware(self, MiddlewareFunc):
        self.GlobalMiddlewares.append(MiddlewareFunc)

    def ErrorHandler(self, StatusCode):
        def Decorator(HandlerFunc):
            self.ErrorHandlers[StatusCode] = HandlerFunc
            return HandlerFunc
        return Decorator

    def MountStatic(self, UrlPrefix, DirectoryPath):
        self.StaticMount = {
            "UrlPrefix": UrlPrefix.rstrip("/"),
            "DirectoryPath": DirectoryPath,
        }

    def Include(self, SubRouter):
        if not isinstance(SubRouter, HellcatRouter):
            raise HellcatRouterError(
                f"Include() expects a HellcatRouter instance, got {type(SubRouter).__name__}"
            )
        self.Routes.extend(SubRouter.Routes)
        self.GlobalMiddlewares.extend(SubRouter.GlobalMiddlewares)
        self.ErrorHandlers.update(SubRouter.ErrorHandlers)

    def Resolve(self, Request):
        for Route in self.Routes:
            PathParams = Route.Match(Request.Path)
            if PathParams is not None:
                return Route, PathParams
        return None, None

    def GetErrorHandler(self, StatusCode):
        return self.ErrorHandlers.get(StatusCode)

    def GetStaticMount(self):
        return self.StaticMount

    def GetGlobalMiddlewares(self):
        return list(self.GlobalMiddlewares)

    def ListRoutes(self):
        return list(self.Routes)

    def __repr__(self):
        return f"<HellcatRouter prefix={self.Prefix!r} routes={len(self.Routes)}>"
