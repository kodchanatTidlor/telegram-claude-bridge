from bridge.recap import escape_md_v2

# Human verb per tool — what Claude is doing right now.
_VERBS = {
    "Bash": "running", "Edit": "editing", "Write": "writing",
    "MultiEdit": "editing", "NotebookEdit": "editing", "Read": "reading",
    "Grep": "searching", "Glob": "finding", "Task": "delegating",
    "WebFetch": "fetching", "WebSearch": "searching the web",
    "ExitPlanMode": "planning", "TodoWrite": "planning",
}
_ARG_KEYS = ("command", "file_path", "path", "pattern", "query", "url",
             "description")   # Task carries a human "description"
ARG_MAX = 120


def _arg(tool_input):
    inp = tool_input or {}
    for key in _ARG_KEYS:
        val = inp.get(key)
        if val:
            return str(val).splitlines()[0][:ARG_MAX]
    return ""


def format_activity(tool_name, tool_input) -> str:
    verb = _VERBS.get(tool_name, tool_name or "working")
    arg = _arg(tool_input)
    head = f"⚙️ {escape_md_v2(verb)}"
    return f"{head} `{escape_md_v2(arg)}`" if arg else head
