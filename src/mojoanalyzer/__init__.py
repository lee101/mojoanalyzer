from importlib.metadata import PackageNotFoundError, version

from .engine import analyze_paths, analyze_sources

try:
    __version__ = version("mojoanalyzer")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__", "analyze_paths", "analyze_sources", "analyze_text"]


def analyze_text(code: str, name: str = "input.mojo", **kw):
    """Analyze one source string; kw as analyze_sources (rule_ids, min_confidence, min_severity, jobs)."""
    return analyze_sources([(name, code)], **kw)
