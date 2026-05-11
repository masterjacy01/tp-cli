from datetime import date

from typer.testing import CliRunner

from tp_cli import __version__
from tp_cli.cli import _fmt_distance, _fmt_duration, _fmt_num, _parse_date, _sport_name, app


def test_version_flag():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"tp-cli {__version__}" in result.output


def test_parse_date_accepts_supported_formats():
    assert _parse_date("2026-05-11") == date(2026, 5, 11)
    assert _parse_date("11.05.2026") == date(2026, 5, 11)
    assert _parse_date("05/11/2026") == date(2026, 5, 11)


def test_formatting_helpers():
    assert _fmt_duration(3661) == "1h 01m"
    assert _fmt_duration(125) == "2m 05s"
    assert _fmt_distance(12345) == "12.3 km"
    assert _fmt_num(42.4) == "42"
    assert _fmt_num(42.45, decimals=1) == "42.5"
    assert _sport_name(2) == "Bike"


def test_workout_help_includes_full_flag():
    result = CliRunner().invoke(app, ["workout", "--help"])

    assert result.exit_code == 0
    assert "--full" in result.output


def test_version_command():
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert f"tp-cli {__version__}" in result.output
