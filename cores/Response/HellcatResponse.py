import json
import os
import mimetypes


class HellcatResponseError(Exception):
    """"""


class HellcatResponseBuildError(HellcatResponseError):
    """"""


class HellcatFileResponseError(HellcatResponseError):
    """"""


StatusMessages = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    204: "No Content",
    206: "Partial Content",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


class HellcatResponse:
    """"""

    def __init__(
        self, Body="", StatusCode=200, ContentType="text/plain; charset=utf-8"
    ):
        self.StatusCode = StatusCode
        self.ContentType = ContentType
        self.Headers = {}
        self.Cookies = []
        self.BodyBytes = b""

        if isinstance(Body, bytes):
            self.BodyBytes = Body
        elif isinstance(Body, str):
            self.BodyBytes = Body.encode("utf-8")
        elif Body is not None:
            raise HellcatResponseBuildError(
                f"Response body must be str or bytes, got {type(Body).__name__}"
            )

    def SetHeader(self, Name, Value):
        self.Headers[Name] = str(Value)
        return self

    def SetCookie(
        self,
        Name,
        Value,
        MaxAge=None,
        Path="/",
        HttpOnly=True,
        SameSite="Lax",
        Secure=False,
    ):
        CookieParts = [f"{Name}={Value}"]
        if MaxAge is not None:
            CookieParts.append(f"Max-Age={MaxAge}")
        if Path:
            CookieParts.append(f"Path={Path}")
        if HttpOnly:
            CookieParts.append("HttpOnly")
        if SameSite:
            CookieParts.append(f"SameSite={SameSite}")
        if Secure:
            CookieParts.append("Secure")
        self.Cookies.append("; ".join(CookieParts))
        return self

    def DeleteCookie(self, Name, Path="/"):
        return self.SetCookie(Name, "", MaxAge=0, Path=Path)

    def Build(self, KeepAlive=False):
        try:
            StatusText = StatusMessages.get(self.StatusCode, "Unknown")
            Lines = [
                f"HTTP/1.1 {self.StatusCode} {StatusText}",
                f"Content-Type: {self.ContentType}",
                f"Content-Length: {len(self.BodyBytes)}",
                "Server: HellcatAPI/1.0",
                "X-Powered-By: HellcatAPI",
            ]

            for HeaderName, HeaderValue in self.Headers.items():
                Lines.append(f"{HeaderName}: {HeaderValue}")

            for CookieValue in self.Cookies:
                Lines.append(f"Set-Cookie: {CookieValue}")

            Lines.append("Connection: keep-alive" if KeepAlive else "Connection: close")
            Lines.append("")
            Lines.append("")

            HeaderSection = "\r\n".join(Lines).encode("utf-8")
            return HeaderSection + self.BodyBytes

        except Exception as Err:
            raise HellcatResponseBuildError(
                f"Failed to build HTTP response (status={self.StatusCode}): {Err}"
            ) from Err

    def __repr__(self):
        return f"<HellcatResponse {self.StatusCode} {self.ContentType}>"


class HellcatJsonResponse(HellcatResponse):
    """"""

    def __init__(self, Data, StatusCode=200):
        try:
            JsonBody = json.dumps(Data, ensure_ascii=False, indent=None)
        except (TypeError, ValueError) as Err:
            raise HellcatResponseBuildError(
                f"JSON serialisation failed: {Err}"
            ) from Err

        super().__init__(
            Body=JsonBody,
            StatusCode=StatusCode,
            ContentType="application/json; charset=utf-8",
        )


class HellcatHtmlResponse(HellcatResponse):
    """"""

    def __init__(self, HtmlContent, StatusCode=200):
        super().__init__(
            Body=HtmlContent,
            StatusCode=StatusCode,
            ContentType="text/html; charset=utf-8",
        )


class HellcatRedirectResponse(HellcatResponse):
    """"""

    def __init__(self, Location, StatusCode=302):
        if not Location:
            raise HellcatResponseBuildError(
                "RedirectResponse requires a non-empty Location"
            )
        super().__init__(Body="", StatusCode=StatusCode)
        self.SetHeader("Location", Location)


class HellcatFileResponse(HellcatResponse):
    """"""

    def __init__(self, FilePath, DownloadAs=None):
        if not os.path.isfile(FilePath):
            raise HellcatFileResponseError(f"File not found: '{FilePath}'")

        MimeType, _ = mimetypes.guess_type(FilePath)
        if MimeType is None:
            MimeType = "application/octet-stream"

        try:
            with open(FilePath, "rb") as FileHandle:
                FileData = FileHandle.read()
        except OSError as Err:
            raise HellcatFileResponseError(
                f"Could not read file '{FilePath}': {Err}"
            ) from Err

        super().__init__(Body=FileData, StatusCode=200, ContentType=MimeType)

        if DownloadAs:
            self.SetHeader(
                "Content-Disposition",
                f'attachment; filename="{DownloadAs}"',
            )


class HellcatErrorResponse(HellcatJsonResponse):
    """"""

    def __init__(self, Message, StatusCode=400, Details=None):
        Payload = {
            "error": True,
            "message": Message,
            "status": StatusCode,
        }
        if Details is not None:
            Payload["details"] = Details

        super().__init__(Data=Payload, StatusCode=StatusCode)


class HellcatStreamResponse:
    """"""

    def __init__(self, GeneratorFunc, ContentType="text/event-stream"):
        if not callable(GeneratorFunc):
            raise HellcatResponseBuildError(
                "StreamResponse GeneratorFunc must be callable"
            )
        self.GeneratorFunc = GeneratorFunc
        self.ContentType = ContentType
        self.StatusCode = 200
        self.Headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }

    def SetHeader(self, Name, Value):
        self.Headers[Name] = str(Value)
        return self

    def BuildHeader(self):
        StatusText = StatusMessages.get(self.StatusCode, "OK")
        Lines = [
            f"HTTP/1.1 {self.StatusCode} {StatusText}",
            f"Content-Type: {self.ContentType}",
            "Transfer-Encoding: chunked",
            "Server: HellcatAPI/1.0",
        ]
        for HeaderName, HeaderValue in self.Headers.items():
            Lines.append(f"{HeaderName}: {HeaderValue}")
        Lines.append("")
        Lines.append("")
        return "\r\n".join(Lines).encode("utf-8")

    def __repr__(self):
        return f"<HellcatStreamResponse {self.ContentType}>"
