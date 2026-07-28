"""elfagent — multi-agent orchestration platform.

Package layout mirrors BUILD_SPEC §7, with one deviation: the platform package
is namespaced under `elfagent.` rather than sitting at the repo root, because a
top-level `platform/` package shadows Python's stdlib `platform` module and
breaks langgraph's imports. The platform/usecases split the spec cares about is
unchanged — only the import prefix differs.
"""

__version__ = "0.1.0"
