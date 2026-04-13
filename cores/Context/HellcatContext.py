import threading
import asyncio
import time
import os
import hashlib
import hmac
import json
import base64


class HellcatSessionStore:
    """"""

    def __init__(self, Ttl=3600):
        self.Store = {}
        self.StoreLock = threading.Lock()
        self.Ttl = Ttl

    def GenerateSessionId(self):
        RandomBytes = os.urandom(32)
        return hashlib.sha256(RandomBytes).hexdigest()

    def Get(self, SessionId):
        with self.StoreLock:
            Entry = self.Store.get(SessionId)
            if Entry is None:
                return {}
            if time.time() > Entry["ExpiresAt"]:
                del self.Store[SessionId]
                return {}
            Entry["ExpiresAt"] = time.time() + self.Ttl
            return dict(Entry["Data"])

    def Set(self, SessionId, Data):
        with self.StoreLock:
            self.Store[SessionId] = {
                "Data": dict(Data),
                "ExpiresAt": time.time() + self.Ttl,
                "CreatedAt": time.time(),
            }

    def Delete(self, SessionId):
        with self.StoreLock:
            self.Store.pop(SessionId, None)

    def Cleanup(self):
        Now = time.time()
        with self.StoreLock:
            ExpiredKeys = [
                Key for Key, Entry in self.Store.items() if Now > Entry["ExpiresAt"]
            ]
            for Key in ExpiredKeys:
                del self.Store[Key]

    def Count(self):
        with self.StoreLock:
            return len(self.Store)

    async def AsyncGet(self, SessionId):
        return self.Get(SessionId)

    async def AsyncSet(self, SessionId, Data):
        self.Set(SessionId, Data)

    async def AsyncDelete(self, SessionId):
        self.Delete(SessionId)


class HellcatJwtUtil:
    """"""

    @staticmethod
    def Base64UrlEncode(Data):
        return base64.urlsafe_b64encode(Data).rstrip(b"=").decode("utf-8")

    @staticmethod
    def Base64UrlDecode(Data):
        Padding = 4 - len(Data) % 4
        if Padding != 4:
            Data += "=" * Padding
        return base64.urlsafe_b64decode(Data)

    @staticmethod
    def Encode(Payload, SecretKey, ExpiresIn=3600):
        Header = {"alg": "HS256", "typ": "JWT"}
        CleanPayload = dict(Payload)
        CleanPayload["exp"] = int(time.time()) + ExpiresIn
        CleanPayload["iat"] = int(time.time())

        HeaderEncoded = HellcatJwtUtil.Base64UrlEncode(
            json.dumps(Header, separators=(",", ":")).encode()
        )
        PayloadEncoded = HellcatJwtUtil.Base64UrlEncode(
            json.dumps(CleanPayload, separators=(",", ":")).encode()
        )

        SigningInput = f"{HeaderEncoded}.{PayloadEncoded}"
        Signature = hmac.new(
            SecretKey.encode("utf-8"), SigningInput.encode("utf-8"), hashlib.sha256
        ).digest()
        SignatureEncoded = HellcatJwtUtil.Base64UrlEncode(Signature)

        return f"{SigningInput}.{SignatureEncoded}"

    @staticmethod
    async def AsyncEncode(Payload, SecretKey, ExpiresIn=3600):
        return HellcatJwtUtil.Encode(Payload, SecretKey, ExpiresIn=ExpiresIn)

    @staticmethod
    async def AsyncDecode(Token, SecretKey):
        return HellcatJwtUtil.Decode(Token, SecretKey)

    @staticmethod
    def Decode(Token, SecretKey):
        try:
            Parts = Token.split(".")
            if len(Parts) != 3:
                return None

            HeaderEncoded, PayloadEncoded, SignatureEncoded = Parts
            SigningInput = f"{HeaderEncoded}.{PayloadEncoded}"

            ExpectedSignature = hmac.new(
                SecretKey.encode("utf-8"), SigningInput.encode("utf-8"), hashlib.sha256
            ).digest()
            ExpectedEncoded = HellcatJwtUtil.Base64UrlEncode(ExpectedSignature)

            if not hmac.compare_digest(SignatureEncoded, ExpectedEncoded):
                return None

            PayloadBytes = HellcatJwtUtil.Base64UrlDecode(PayloadEncoded)
            Payload = json.loads(PayloadBytes.decode("utf-8"))

            if "exp" in Payload and time.time() > Payload["exp"]:
                return None

            return Payload

        except Exception:
            return None


class HellcatRequestContext(threading.local):
    """"""

    def __init__(self):
        super().__init__()
        self.Data = {}

    def Set(self, Key, Value):
        self.Data[Key] = Value

    def Get(self, Key, Default=None):
        return self.Data.get(Key, Default)

    def Has(self, Key):
        return Key in self.Data

    def Clear(self):
        self.Data.clear()

    def All(self):
        return dict(self.Data)

    async def AsyncSet(self, Key, Value):
        self.Set(Key, Value)

    async def AsyncGet(self, Key, Default=None):
        return self.Get(Key, Default)


RequestContext = HellcatRequestContext()
