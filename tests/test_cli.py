import pytest

from radar.__main__ import COMMANDS, HANDLERS, main


def test_help_lists_all_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in COMMANDS:
        assert name in out


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", [c for c in COMMANDS if c not in HANDLERS])
def test_stub_commands_report_not_implemented(command, capsys):
    assert main([command]) == 1
    assert "not implemented yet" in capsys.readouterr().err
