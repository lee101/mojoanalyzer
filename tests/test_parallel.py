from pathlib import Path

from mojoanalyzer.engine import analyze_sources

SRC = [(f"f{i}.mojo", Path(p).read_text()) for i, p in enumerate(sorted(Path("tests/fixtures").rglob("*.mojo")))]


def test_parallel_equals_serial():
    assert len(SRC) >= 12
    serial = analyze_sources(SRC, None, "low", "info", jobs=1)
    par = analyze_sources(SRC, None, "low", "info", jobs=4)
    assert [f.to_dict() for f in serial] == [f.to_dict() for f in par]
