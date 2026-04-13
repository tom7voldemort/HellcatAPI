import urllib.parse
import json


class HellcatRequestError(Exception):
    """"""


class HellcatRequestParseError(HellcatRequestError):
    """"""


class HellcatMultipartError(HellcatRequestError):
    """"""


class HellcatJsonDecodeError(HellcatRequestError):
    """"""


class HellcatUploadedFile:
    """"""

    def __init__(self, Filename, ContentType, Data):
        if not isinstance(Data, bytes):
            raise HellcatRequestError(
                f"UploadedFile data must be bytes, got {type(Data).__name__}"
            )
        self.Filename = Filename
        self.ContentType = ContentType
        self.Data = Data
        self.Size = len(Data)

    def Save(self, DestinationPath):
        try:
            with open(DestinationPath, "wb") as FileHandle:
                FileHandle.write(self.Data)
        except OSError as Err:
            raise HellcatRequestError(
                f"Failed to save uploaded file '{self.Filename}' "
                f"to '{DestinationPath}': {Err}"
            ) from Err

    def __repr__(self):
        return f"<HellcatUploadedFile name={self.Filename!r} size={self.Size}>"


class HellcatRequest:
    """"""

    def __init__(self):
        self.Method = ""
        self.Path = ""
        self.HttpVersion = "HTTP/1.1"
        self.Headers = {}
        self.QueryParams = {}
        self.PathParams = {}
        self.Body = b""
        self.Form = {}
        self.Files = {}
        self.Json = None
        self.RemoteAddress = ("", 0)
        self.Cookies = {}
        self.Session = {}

    @property
    def ContentType(self):
        return self.Headers.get("content-type", "")

    @property
    def ContentLength(self):
        try:
            return int(self.Headers.get("content-length", 0))
        except (ValueError, TypeError):
            return 0

    @property
    def IsJson(self):
        return "application/json" in self.ContentType

    @property
    def IsForm(self):
        return "application/x-www-form-urlencoded" in self.ContentType

    @property
    def IsMultipart(self):
        return "multipart/form-data" in self.ContentType

    @property
    def Host(self):
        return self.Headers.get("host", "")

    @property
    def UserAgent(self):
        return self.Headers.get("user-agent", "")

    @property
    def Authorization(self):
        return self.Headers.get("authorization", "")

    @property
    def RemoteIp(self):
        return self.RemoteAddress[0]

    def GetHeader(self, Name, Default=None):
        return self.Headers.get(Name.lower(), Default)

    def GetQuery(self, Key, Default=None):
        return self.QueryParams.get(Key, Default)

    def GetForm(self, Key, Default=None):
        return self.Form.get(Key, Default)

    def GetJson(self):
        if self.Json is not None:
            return self.Json
        try:
            self.Json = json.loads(self.Body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.Json = None
        return self.Json

    def RequireJson(self):
        Data = self.GetJson()
        if Data is None:
            raise HellcatJsonDecodeError("Request body could not be decoded as JSON")
        return Data

    def GetFile(self, FieldName):
        return self.Files.get(FieldName)

    def RequireFile(self, FieldName):
        File = self.Files.get(FieldName)
        if File is None:
            raise HellcatRequestError(
                f"Expected file upload for field '{FieldName}' but it was not found"
            )
        return File

    def __repr__(self):
        return f"<HellcatRequest {self.Method} {self.Path}>"


class HellcatRequestParser:
    """"""

    @staticmethod
    def Parse(RawData, RemoteAddress):
        Request = HellcatRequest()
        Request.RemoteAddress = RemoteAddress

        if not RawData:
            raise HellcatRequestParseError("Empty request data received")

        try:
            HeaderSection, Body = HellcatRequestParser.SplitHeaderBody(RawData)
            Request.Body = Body

            Lines = HeaderSection.split("\r\n")
            if not Lines or not Lines[0].strip():
                raise HellcatRequestParseError("Missing HTTP request line")

            HellcatRequestParser.ParseRequestLine(Request, Lines[0])
            HellcatRequestParser.ParseHeaders(Request, Lines[1:])
            HellcatRequestParser.ParseCookies(Request)
            HellcatRequestParser.ParseBody(Request)

        except HellcatRequestParseError:
            raise

        except UnicodeDecodeError as Err:
            raise HellcatRequestParseError(
                f"Request contains non-UTF-8 bytes in headers: {Err}"
            ) from Err

        except Exception as Err:
            raise HellcatRequestParseError(
                f"Unexpected error while parsing request: {Err}"
            ) from Err

        return Request

    @staticmethod
    def SplitHeaderBody(RawData):
        Separator = b"\r\n\r\n"
        SepIndex = RawData.find(Separator)
        if SepIndex == -1:
            return RawData.decode("utf-8", errors="replace"), b""
        HeaderBytes = RawData[:SepIndex]
        BodyBytes = RawData[SepIndex + len(Separator):]
        return HeaderBytes.decode("utf-8", errors="replace"), BodyBytes

    @staticmethod
    def ParseRequestLine(Request, Line):
        Parts = Line.strip().split(" ", 2)
        if len(Parts) < 2:
            raise HellcatRequestParseError(
                f"Malformed HTTP request line: '{Line.strip()}'"
            )

        Request.Method = Parts[0].upper()
        FullPath = Parts[1]
        Request.HttpVersion = Parts[2] if len(Parts) > 2 else "HTTP/1.1"

        if "?" in FullPath:
            PathOnly, QueryString = FullPath.split("?", 1)
            Request.Path = urllib.parse.unquote(PathOnly)
            Request.QueryParams = dict(urllib.parse.parse_qsl(QueryString))
        else:
            Request.Path = urllib.parse.unquote(FullPath)
            Request.QueryParams = {}

    @staticmethod
    def ParseHeaders(Request, Lines):
        for Line in Lines:
            if ": " in Line:
                Key, Value = Line.split(": ", 1)
                Request.Headers[Key.lower().strip()] = Value.strip()

    @staticmethod
    def ParseCookies(Request):
        CookieHeader = Request.Headers.get("cookie", "")
        if not CookieHeader:
            return
        for Pair in CookieHeader.split(";"):
            Pair = Pair.strip()
            if "=" in Pair:
                CName, CValue = Pair.split("=", 1)
                Request.Cookies[CName.strip()] = CValue.strip()

    @staticmethod
    def ParseBody(Request):
        if Request.IsJson:
            Request.GetJson()
        elif Request.IsForm:
            HellcatRequestParser.ParseFormUrlEncoded(Request)
        elif Request.IsMultipart:
            HellcatRequestParser.ParseMultipart(Request)

    @staticmethod
    def ParseFormUrlEncoded(Request):
        try:
            BodyStr = Request.Body.decode("utf-8")
            Request.Form = dict(urllib.parse.parse_qsl(BodyStr))
        except UnicodeDecodeError:
            Request.Form = {}

    @staticmethod
    def ParseMultipart(Request):
        ContentType = Request.ContentType
        if "boundary=" not in ContentType:
            return

        BoundaryStr = ContentType.split("boundary=")[-1].strip()
        Boundary = ("--" + BoundaryStr).encode()
        Parts = Request.Body.split(Boundary)

        for Part in Parts[1:]:
            if Part.strip() in (b"", b"--", b"--\r\n"):
                continue
            if Part.startswith(b"\r\n"):
                Part = Part[2:]
            if Part.endswith(b"\r\n--"):
                Part = Part[:-4]
            elif Part.endswith(b"\r\n"):
                Part = Part[:-2]

            PartSep = Part.find(b"\r\n\r\n")
            if PartSep == -1:
                continue

            PartHeaders = Part[:PartSep].decode("utf-8", errors="replace")
            PartBody = Part[PartSep + 4:]

            Disposition = ""
            PartContentType = "application/octet-stream"

            for HLine in PartHeaders.split("\r\n"):
                LowerLine = HLine.lower()
                if LowerLine.startswith("content-disposition:"):
                    Disposition = HLine
                elif LowerLine.startswith("content-type:"):
                    PartContentType = HLine.split(":", 1)[1].strip()

            FieldName = HellcatRequestParser.ExtractDispositionParam(Disposition, "name")
            Filename = HellcatRequestParser.ExtractDispositionParam(Disposition, "filename")

            if not FieldName:
                continue

            if Filename:
                try:
                    Request.Files[FieldName] = HellcatUploadedFile(
                        Filename=Filename,
                        ContentType=PartContentType,
                        Data=PartBody,
                    )
                except HellcatRequestError:
                    pass
            else:
                try:
                    Request.Form[FieldName] = PartBody.decode("utf-8")
                except UnicodeDecodeError:
                    Request.Form[FieldName] = PartBody

    @staticmethod
    def ExtractDispositionParam(Disposition, ParamName):
        SearchKey = ParamName + '="'
        if SearchKey not in Disposition:
            return None
        try:
            Start = Disposition.index(SearchKey) + len(SearchKey)
            End = Disposition.index('"', Start)
            return Disposition[Start:End]
        except ValueError:
            return None
