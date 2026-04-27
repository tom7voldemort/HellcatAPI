import asyncio
import inspect

from cores.Response.HellcatResponse import (
    HellcatResponse,
    HellcatHtmlResponse,
    HellcatJsonResponse,
    HellcatErrorResponse,
)


def IsCoroutineFunction(Func):
    return asyncio.iscoroutinefunction(Func) or inspect.iscoroutinefunction(Func)


def RunCoroutine(Coro):
    Loop = asyncio.new_event_loop()
    try:
        return Loop.run_until_complete(Coro)
    finally:
        try:
            PendingTasks = asyncio.all_tasks(Loop)
            if PendingTasks:
                Loop.run_until_complete(
                    asyncio.gather(*PendingTasks, return_exceptions=True)
                )
        finally:
            Loop.close()


def NormaliseResponse(Result):
    if Result is None:
        return HellcatResponse(Body="", StatusCode=204)
    if isinstance(Result, str):
        return HellcatHtmlResponse(Result)
    if isinstance(Result, dict):
        return HellcatJsonResponse(Result)
    if isinstance(Result, tuple):
        return ParseTuple(Result)
    return Result


def ParseTuple(TupleResult):
    def MakeResponse(Body, Status):
        if isinstance(Body, dict):
            return HellcatJsonResponse(Body, StatusCode=Status)
        if isinstance(Body, str):
            return HellcatHtmlResponse(Body, StatusCode=Status)
        return HellcatResponse(Body=Body, StatusCode=Status)

    if len(TupleResult) == 2:
        Body, Status = TupleResult
        return MakeResponse(Body, Status)
    if len(TupleResult) == 3:
        Body, Status, Headers = TupleResult
        Resp = MakeResponse(Body, Status)
        if isinstance(Headers, dict):
            for K, V in Headers.items():
                Resp.SetHeader(K, V)
        return Resp
    return HellcatErrorResponse("Invalid async response tuple format", StatusCode=500)


def CallHandler(Handler, Request):
    if IsCoroutineFunction(Handler):
        return NormaliseResponse(RunCoroutine(Handler(Request)))
    return NormaliseResponse(Handler(Request))


async def BuildPipeline(Request, FinalHandler, Middlewares):
    async def BuildChain(Index):
        if Index >= len(Middlewares):
            if IsCoroutineFunction(FinalHandler):
                return await FinalHandler(Request)
            return FinalHandler(Request)

        CurrentMiddleware = Middlewares[Index]

        async def AsyncNext(Req):
            return await BuildChain(Index + 1)

        if IsCoroutineFunction(CurrentMiddleware):
            return await CurrentMiddleware(Request, AsyncNext)

        Result = CurrentMiddleware(Request, AsyncNext)
        if inspect.iscoroutine(Result):
            return await Result
        return Result

    return await BuildChain(0)


def RunAsyncPipeline(Request, FinalHandler, Middlewares):
    Result = RunCoroutine(BuildPipeline(Request, FinalHandler, Middlewares))
    return NormaliseResponse(Result)


def HasAnyAsync(Middlewares, Handler):
    if IsCoroutineFunction(Handler):
        return True
    return any(IsCoroutineFunction(M) for M in Middlewares)


async def CallWithTimeout(Coro, TimeoutSeconds):
    try:
        return await asyncio.wait_for(Coro, timeout=TimeoutSeconds)
    except asyncio.TimeoutError:
        raise HellcatAsyncTimeoutError(
            "Coroutine timed out", TimeoutSeconds=TimeoutSeconds
        )


async def GatherSafe(*Coroutines):
    Results = await asyncio.gather(*Coroutines, return_exceptions=False)
    return Results


def HellcatAsyncError(Message, StatusCode=500):
    return HellcatErrorResponse(Message, StatusCode=StatusCode)


def HellcatCoroutineError(Message):
    Exc = RuntimeError(f"[HellcatAsync] Coroutine error: {Message}")
    Exc.__class__.__name__ = "HellcatCoroutineError"
    return Exc


def HellcatEventLoopError(Message):
    Exc = RuntimeError(f"[HellcatAsync] Event loop error: {Message}")
    Exc.__class__.__name__ = "HellcatEventLoopError"
    return Exc


def HellcatAsyncMiddlewareError(Message):
    Exc = RuntimeError(f"[HellcatAsync] Middleware error: {Message}")
    Exc.__class__.__name__ = "HellcatAsyncMiddlewareError"
    return Exc


def HellcatAsyncTimeoutError(Message, TimeoutSeconds=None):
    Detail = f" (timeout={TimeoutSeconds}s)" if TimeoutSeconds else ""
    Exc = TimeoutError(f"[HellcatAsync] Timed out{Detail}: {Message}")
    Exc.__class__.__name__ = "HellcatAsyncTimeoutError"
    return Exc
