import os
import re
import html
import asyncio


class HellcatTemplateError(Exception):
    """"""


class HellcatTemplateNotFoundError(HellcatTemplateError):
    """"""


class HellcatTemplateRenderError(HellcatTemplateError):
    """"""


class HellcatTemplateIncludeError(HellcatTemplateError):
    """"""


class HellcatTemplateExtendsError(HellcatTemplateError):
    """"""


class HellcatTemplateEngine:
    """"""

    def __init__(self, TemplateDirectory="templates"):
        self.TemplateDirectory = TemplateDirectory
        self.Cache = {}

    def LoadFile(self, TemplateName):
        if not self.TemplateDirectory:
            raise HellcatTemplateNotFoundError(
                f"Cannot load '{TemplateName}': no TemplateDirectory configured"
            )

        FilePath = os.path.join(self.TemplateDirectory, TemplateName)
        if not os.path.isfile(FilePath):
            raise HellcatTemplateNotFoundError(f"Template not found: '{FilePath}'")

        try:
            CurrentMtime = os.path.getmtime(FilePath)
        except OSError:
            CurrentMtime = None

        Cached = self.Cache.get(TemplateName)
        if Cached and Cached.get("Mtime") == CurrentMtime:
            return Cached["Content"]

        try:
            with open(FilePath, "r", encoding="utf-8") as FileHandle:
                Content = FileHandle.read()
        except OSError as Err:
            raise HellcatTemplateError(
                f"Could not read template file '{FilePath}': {Err}"
            ) from Err

        self.Cache[TemplateName] = {"Content": Content, "Mtime": CurrentMtime}
        return Content

    def ClearCache(self):
        self.Cache.clear()

    def Render(self, TemplateName, Context=None):
        if Context is None:
            Context = {}
        Source = self.LoadFile(TemplateName)
        return self.RenderString(Source, Context, SourceName=TemplateName)

    def RenderString(self, Source, Context=None, SourceName="<string>"):
        if Context is None:
            Context = {}

        try:
            Source = self.ProcessComments(Source)
            Source = self.ProcessExtends(Source, Context)
            Source = self.ProcessIncludes(Source, Context)
            Source = self.ProcessControlFlow(Source, Context)
            Source = self.ProcessVariables(Source, Context)
            return Source

        except (
            HellcatTemplateNotFoundError,
            HellcatTemplateIncludeError,
            HellcatTemplateExtendsError,
        ):
            raise

        except HellcatTemplateRenderError:
            raise

        except Exception as Err:
            raise HellcatTemplateRenderError(
                f"Render error in '{SourceName}': {Err}"
            ) from Err

    def ProcessComments(self, Source):
        return re.sub(r"\{#.*?#\}", "", Source, flags=re.DOTALL)

    def ProcessExtends(self, Source, Context):
        ExtendsMatch = re.search(r'\{%\s*extends\s+"([^"]+)"\s*%\}', Source)
        if not ExtendsMatch:
            return Source

        ParentName = ExtendsMatch.group(1)
        try:
            ParentSource = self.LoadFile(ParentName)
        except HellcatTemplateNotFoundError as Err:
            raise HellcatTemplateExtendsError(
                f"Parent template not found in extends directive: {Err}"
            ) from Err

        ChildBlocks = {}
        for BlockMatch in re.finditer(
            r"\{%\s*block\s+(\w+)\s*%\}(.*?)\{%\s*endblock\s*%\}",
            Source,
            flags=re.DOTALL,
        ):
            ChildBlocks[BlockMatch.group(1)] = BlockMatch.group(2)

        def ReplaceParentBlock(Match):
            BlockName = Match.group(1)
            DefaultContent = Match.group(2)
            return ChildBlocks.get(BlockName, DefaultContent)

        Result = re.sub(
            r"\{%\s*block\s+(\w+)\s*%\}(.*?)\{%\s*endblock\s*%\}",
            ReplaceParentBlock,
            ParentSource,
            flags=re.DOTALL,
        )
        return Result

    def ProcessIncludes(self, Source, Context):
        def ReplaceInclude(Match):
            IncludedName = Match.group(1)
            try:
                IncludedSource = self.LoadFile(IncludedName)
            except HellcatTemplateNotFoundError as Err:
                raise HellcatTemplateIncludeError(
                    f"Included template not found: {Err}"
                ) from Err
            return self.RenderString(IncludedSource, Context, SourceName=IncludedName)

        return re.sub(
            r'\{%\s*include\s+"([^"]+)"\s*%\}',
            ReplaceInclude,
            Source,
        )

    def ProcessControlFlow(self, Source, Context):
        Source = self.ProcessForLoops(Source, Context)
        Source = self.ProcessIfBlocks(Source, Context)
        return Source

    def SafeEval(self, Expression, Context):
        SafeGlobals = {"__builtins__": {}}
        SafeLocals = dict(Context)
        SafeBuiltins = {
            "len": len,
            "range": range,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "reversed": reversed,
            "isinstance": isinstance,
            "None": None,
            "True": True,
            "False": False,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
        }
        SafeLocals.update(SafeBuiltins)
        try:
            return eval(Expression.strip(), SafeGlobals, SafeLocals)
        except Exception:
            return None

    def ProcessForLoops(self, Source, Context):
        Pattern = re.compile(
            r"\{%\s*for\s+(\w+)\s+in\s+(.+?)\s*%\}(.*?)\{%\s*endfor\s*%\}",
            re.DOTALL,
        )

        def ExpandLoop(Match):
            VarName = Match.group(1)
            IterableExpr = Match.group(2)
            Body = Match.group(3)
            Iterable = self.SafeEval(IterableExpr, Context)

            if Iterable is None or not hasattr(Iterable, "__iter__"):
                return ""

            Parts = []
            try:
                for Item in Iterable:
                    LoopContext = dict(Context)
                    LoopContext[VarName] = Item
                    Parts.append(self.ProcessForLoops(Body, LoopContext))
            except TypeError:
                pass

            return "".join(Parts)

        return Pattern.sub(ExpandLoop, Source)

    def ProcessIfBlocks(self, Source, Context):
        Pattern = re.compile(
            r"\{%\s*if\s+(.+?)\s*%\}(.*?)\{%\s*endif\s*%\}",
            re.DOTALL,
        )

        def EvaluateIf(Match):
            Condition = Match.group(1)
            Body = Match.group(2)

            ElifPattern = re.compile(r"^(.*?)\{%\s*elif\s+(.+?)\s*%\}(.*)", re.DOTALL)
            ElsePattern = re.compile(r"^(.*?)\{%\s*else\s*%\}(.*)", re.DOTALL)

            if self.SafeEval(Condition, Context):
                ElseMatch = ElsePattern.match(Body)
                if ElseMatch:
                    Body = ElseMatch.group(1)
                ElifMatch = ElifPattern.match(Body)
                if ElifMatch:
                    Body = ElifMatch.group(1)
                return self.ProcessIfBlocks(Body, Context)

            ElifMatch = ElifPattern.match(Body)
            if ElifMatch:
                return self.ProcessIfBlocks(
                    "{%% if %s %%}%s{%% endif %%}" % (ElifMatch.group(2), ElifMatch.group(3)),
                    Context,
                )

            ElseMatch = ElsePattern.match(Body)
            if ElseMatch:
                return self.ProcessIfBlocks(ElseMatch.group(2), Context)

            return ""

        return Pattern.sub(EvaluateIf, Source)

    def ProcessVariables(self, Source, Context):
        def ReplaceVariable(Match):
            Expression = Match.group(1).strip()
            RawMode = False

            if Expression.endswith("| raw"):
                Expression = Expression[:-5].strip()
                RawMode = True

            Value = self.ResolveExpression(Expression, Context)
            if Value is None:
                return ""

            StringValue = str(Value)
            return StringValue if RawMode else html.escape(StringValue)

        return re.sub(r"\{\{(.+?)\}\}", ReplaceVariable, Source)

    def ResolveExpression(self, Expression, Context):
        Parts = Expression.split(".")
        Value = self.SafeEval(Parts[0], Context)
        if Value is None and Parts[0] not in Context:
            return None

        for Part in Parts[1:]:
            if Value is None:
                return None
            try:
                Value = getattr(Value, Part)
                continue
            except AttributeError:
                pass
            try:
                Value = Value[Part]
                continue
            except (KeyError, TypeError):
                pass
            try:
                Value = Value[int(Part)]
            except (ValueError, IndexError, TypeError):
                return None

        return Value
