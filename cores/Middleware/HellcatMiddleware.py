import time
import threading
import hashlib
import os
import gzip
import json
import base64
import asyncio
import inspect

from cores.Response.HellcatResponse import (
    HellcatResponse,
    HellcatErrorResponse,
    HellcatStreamResponse,
)


def IsAsyncFunc(Func):
    return asyncio.iscoroutinefunction(Func) or inspect.iscoroutinefunction(Func)


async def AwaitNext(Next, Request):
    if IsAsyncFunc(Next):
        return await Next(Request)
    return Next(Request)


class HellcatMiddlewareError(Exception):
    """"""


class HellcatAuthError(HellcatMiddlewareError):
    """"""


class HellcatCsrfError(HellcatMiddlewareError):
    """"""


class HellcatCorsMiddleware:
    """"""

    def __init__(
        self,
        AllowedOrigins=None,
        AllowedMethods=None,
        AllowedHeaders=None,
        AllowCredentials=False,
        MaxAge=86400,
    ):
        self.AllowedOrigins = AllowedOrigins or ["*"]
        self.AllowedMethods = AllowedMethods or [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "OPTIONS",
        ]
        self.AllowedHeaders = AllowedHeaders or [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
        ]
        self.AllowCredentials = AllowCredentials
        self.MaxAge = MaxAge

    def __call__(self, Request, Next):
        Origin = Request.GetHeader("Origin", "*")

        if Request.Method == "OPTIONS":
            Response = HellcatResponse(
                Body="", StatusCode=204, ContentType="text/plain"
            )
            self.AddCorsHeaders(Response, Origin)
            return Response

        if IsAsyncFunc(Next):
            async def AsyncCors(Req):
                Resp = await AwaitNext(Next, Req)
                self.AddCorsHeaders(Resp, Origin)
                return Resp
            return AsyncCors(Request)

        Response = Next(Request)
        self.AddCorsHeaders(Response, Origin)
        return Response

    def AddCorsHeaders(self, Response, Origin):
        if "*" in self.AllowedOrigins:
            AllowedOrigin = "*"
        elif Origin in self.AllowedOrigins:
            AllowedOrigin = Origin
        else:
            AllowedOrigin = self.AllowedOrigins[0] if self.AllowedOrigins else "*"

        Response.SetHeader("Access-Control-Allow-Origin", AllowedOrigin)
        Response.SetHeader(
            "Access-Control-Allow-Methods", ", ".join(self.AllowedMethods)
        )
        Response.SetHeader(
            "Access-Control-Allow-Headers", ", ".join(self.AllowedHeaders)
        )
        Response.SetHeader("Access-Control-Max-Age", str(self.MaxAge))
        if self.AllowCredentials:
            Response.SetHeader("Access-Control-Allow-Credentials", "true")


class HellcatRateLimitMiddleware:
    """"""

    def __init__(self, MaxRequests=100, WindowSeconds=60):
        if MaxRequests < 1:
            raise HellcatMiddlewareError("MaxRequests must be at least 1")
        if WindowSeconds < 1:
            raise HellcatMiddlewareError("WindowSeconds must be at least 1")

        self.MaxRequests = MaxRequests
        self.WindowSeconds = WindowSeconds
        self.Counters = {}
        self.Lock = threading.Lock()

    def __call__(self, Request, Next):
        Ip = Request.RemoteAddress[0]
        Now = time.time()

        with self.Lock:
            if Ip not in self.Counters:
                self.Counters[Ip] = []

            WindowStart = Now - self.WindowSeconds
            self.Counters[Ip] = [T for T in self.Counters[Ip] if T > WindowStart]

            if len(self.Counters[Ip]) >= self.MaxRequests:
                RetryAfter = int(self.Counters[Ip][0] + self.WindowSeconds - Now) + 1
                Response = HellcatErrorResponse(
                    f"Rate limit exceeded. Try again in {RetryAfter} seconds.",
                    StatusCode=429,
                )
                Response.SetHeader("Retry-After", str(RetryAfter))
                return Response

            self.Counters[Ip].append(Now)

        if IsAsyncFunc(Next):
            async def AsyncRateLimit(Req):
                return await AwaitNext(Next, Req)
            return AsyncRateLimit(Request)
        return Next(Request)


class HellcatBasicAuthMiddleware:
    """"""

    def __init__(self, Username, Password, Realm="HellcatAPI"):
        if not Username or not Password:
            raise HellcatAuthError(
                "BasicAuthMiddleware requires both a Username and Password"
            )
        self.Username = Username
        self.PasswordHash = hashlib.sha256(Password.encode()).hexdigest()
        self.Realm = Realm

    def __call__(self, Request, Next):
        AuthHeader = Request.Authorization
        if not AuthHeader or not AuthHeader.startswith("Basic "):
            return self.ChallengeResponse()

        try:
            Decoded = base64.b64decode(AuthHeader[6:]).decode("utf-8")
            User, Pw = Decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            return self.ChallengeResponse()

        InputHash = hashlib.sha256(Pw.encode()).hexdigest()
        if User != self.Username or InputHash != self.PasswordHash:
            return self.ChallengeResponse()

        if IsAsyncFunc(Next):
            async def AsyncBasic(Req):
                return await AwaitNext(Next, Req)
            return AsyncBasic(Request)
        return Next(Request)

    def ChallengeResponse(self):
        Response = HellcatResponse(
            Body="Authentication required",
            StatusCode=401,
            ContentType="text/plain; charset=utf-8",
        )
        Response.SetHeader("WWW-Authenticate", f'Basic realm="{self.Realm}"')
        return Response


class HellcatBearerAuthMiddleware:
    """"""

    def __init__(self, ValidTokens=None, ValidatorFunc=None):
        if not ValidTokens and not ValidatorFunc:
            raise HellcatAuthError(
                "BearerAuthMiddleware requires either ValidTokens or ValidatorFunc"
            )
        self.ValidTokens = set(ValidTokens or [])
        self.ValidatorFunc = ValidatorFunc

    def __call__(self, Request, Next):
        AuthHeader = Request.Authorization
        if not AuthHeader or not AuthHeader.startswith("Bearer "):
            return HellcatErrorResponse(
                "Authentication token is required", StatusCode=401
            )

        Token = AuthHeader[7:].strip()
        if not Token:
            return HellcatErrorResponse(
                "Bearer token must not be empty", StatusCode=401
            )

        try:
            if self.ValidatorFunc:
                Valid = self.ValidatorFunc(Token)
            else:
                Valid = Token in self.ValidTokens
        except Exception:
            return HellcatErrorResponse(
                "Token validation failed due to an internal error", StatusCode=500
            )

        if not Valid:
            return HellcatErrorResponse("Invalid or expired token", StatusCode=401)

        if IsAsyncFunc(Next):
            async def AsyncBearer(Req):
                return await AwaitNext(Next, Req)
            return AsyncBearer(Request)
        return Next(Request)


class HellcatBodySizeLimitMiddleware:
    """"""

    def __init__(self, MaxBytes=10 * 1024 * 1024):
        if MaxBytes < 1:
            raise HellcatMiddlewareError("MaxBytes must be at least 1")
        self.MaxBytes = MaxBytes

    def __call__(self, Request, Next):
        BodySize = len(Request.Body)
        if BodySize > self.MaxBytes:
            return HellcatErrorResponse(
                f"Request body too large: {BodySize} bytes received, "
                f"maximum allowed is {self.MaxBytes} bytes.",
                StatusCode=413,
            )
        if IsAsyncFunc(Next):
            async def AsyncBodyLimit(Req):
                return await AwaitNext(Next, Req)
            return AsyncBodyLimit(Request)
        return Next(Request)


class HellcatGzipMiddleware:
    """"""

    def __init__(self, MinSizeBytes=1024):
        self.MinSizeBytes = MinSizeBytes

    def __call__(self, Request, Next):
        if IsAsyncFunc(Next):
            async def AsyncGzip(Req):
                Response = await AwaitNext(Next, Req)
                return self.Compress(Request, Response)
            return AsyncGzip(Request)

        Response = Next(Request)
        return self.Compress(Request, Response)

    def Compress(self, Request, Response):
        AcceptEncoding = Request.GetHeader("Accept-Encoding", "")
        if "gzip" not in AcceptEncoding:
            return Response
        if isinstance(Response, HellcatStreamResponse):
            return Response
        BodyBytes = getattr(Response, "BodyBytes", b"")
        if len(BodyBytes) < self.MinSizeBytes:
            return Response
        try:
            Compressed = gzip.compress(BodyBytes)
            Response.BodyBytes = Compressed
            Response.SetHeader("Content-Encoding", "gzip")
            Response.SetHeader("Vary", "Accept-Encoding")
        except (OSError, gzip.BadGzipFile):
            pass
        return Response


class HellcatSecurityHeadersMiddleware:
    """"""

    def __call__(self, Request, Next):
        if IsAsyncFunc(Next):
            async def AsyncSec(Req):
                Resp = await AwaitNext(Next, Req)
                return self.ApplyHeaders(Resp)
            return AsyncSec(Request)
        return self.ApplyHeaders(Next(Request))

    def ApplyHeaders(self, Response):
        Response.SetHeader("X-Content-Type-Options", "nosniff")
        Response.SetHeader("X-Frame-Options", "DENY")
        Response.SetHeader("X-XSS-Protection", "1; mode=block")
        Response.SetHeader("Referrer-Policy", "strict-origin-when-cross-origin")
        Response.SetHeader(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        return Response


class HellcatCsrfMiddleware:
    """"""

    SafeMethods = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    def __init__(self, SecretKey, CookieName="hellcat_csrf", HeaderName="X-Csrf-Token"):
        if not SecretKey:
            raise HellcatCsrfError("CsrfMiddleware requires a non-empty SecretKey")
        self.SecretKey = SecretKey
        self.CookieName = CookieName
        self.HeaderName = HeaderName.lower()

    def GenerateToken(self):
        return hashlib.sha256(os.urandom(32) + self.SecretKey.encode()).hexdigest()

    def __call__(self, Request, Next):
        if Request.Method in self.SafeMethods:
            if IsAsyncFunc(Next):
                async def AsyncCsrfSafe(Req):
                    Resp = await AwaitNext(Next, Req)
                    if self.CookieName not in Req.Cookies:
                        Token = self.GenerateToken()
                        Resp.SetCookie(
                            self.CookieName, Token, HttpOnly=False, SameSite="Strict"
                        )
                    return Resp
                return AsyncCsrfSafe(Request)

            Response = Next(Request)
            if self.CookieName not in Request.Cookies:
                Token = self.GenerateToken()
                Response.SetCookie(
                    self.CookieName, Token, HttpOnly=False, SameSite="Strict"
                )
            return Response

        CookieToken = Request.Cookies.get(self.CookieName)
        HeaderToken = Request.GetHeader(self.HeaderName)

        if not CookieToken:
            return HellcatErrorResponse("CSRF cookie is missing", StatusCode=403)
        if not HeaderToken:
            return HellcatErrorResponse(
                f"CSRF header '{self.HeaderName}' is missing", StatusCode=403
            )
        if CookieToken != HeaderToken:
            return HellcatErrorResponse("CSRF token mismatch", StatusCode=403)

        if IsAsyncFunc(Next):
            async def AsyncCsrf(Req):
                return await AwaitNext(Next, Req)
            return AsyncCsrf(Request)
        return Next(Request)


class HellcatJsonValidatorMiddleware:
    """"""

    def __init__(self, RequiredFields=None, Schema=None):
        self.RequiredFields = RequiredFields or []
        self.Schema = Schema or {}

    def __call__(self, Request, Next):
        if not Request.IsJson:
            return HellcatErrorResponse(
                "Content-Type must be 'application/json'",
                StatusCode=415,
            )

        Data = Request.GetJson()
        if Data is None:
            return HellcatErrorResponse(
                "Request body is not valid JSON", StatusCode=400
            )

        if not isinstance(Data, dict):
            return HellcatErrorResponse(
                "JSON body must be an object (dict), not an array or primitive",
                StatusCode=422,
            )

        for FieldName in self.RequiredFields:
            if FieldName not in Data:
                return HellcatErrorResponse(
                    f"Required field '{FieldName}' is missing from the request body",
                    StatusCode=422,
                )

        for FieldName, ExpectedType in self.Schema.items():
            if FieldName in Data and not isinstance(Data[FieldName], ExpectedType):
                return HellcatErrorResponse(
                    f"Field '{FieldName}' must be of type "
                    f"'{ExpectedType.__name__}', "
                    f"got '{type(Data[FieldName]).__name__}'",
                    StatusCode=422,
                )

        if IsAsyncFunc(Next):
            async def AsyncJsonValidator(Req):
                return await AwaitNext(Next, Req)
            return AsyncJsonValidator(Request)
        return Next(Request)
