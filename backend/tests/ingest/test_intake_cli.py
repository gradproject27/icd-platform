import json

from app.ingest.cli import main


def test_summary(sample, capsys):
    assert main(["unsw-nb15", str(sample)]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "Records read 30" in out
    assert "labelled 22 (flagged 13, unflagged 9)" in out
    assert "unlabelled 1" in out
    assert "Quarantined 7" in out


def test_json(sample, capsys):
    assert main(["unsw-nb15", str(sample), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["counts"]["records_read"] == 30
    assert result["seconds"] >= 0


def test_profile_has_no_entity_values(sample, capsys):
    assert main(["unsw-nb15", str(sample), "--profile"]) == 0
    out = capsys.readouterr().out
    profile = json.loads(out)
    assert profile["value_counts"]["Label"]["1"] == 13
    assert profile["value_counts"]["attack_cat"][" Fuzzers "] == 1
    assert "192.0.2." not in out and "198.51.100." not in out and "203.0.113." not in out


def test_show_record(sample, capsys):
    assert main(["unsw-nb15", str(sample), "--show-record", "unsw-nb15-sample.csv:29"]) == 0
    assert capsys.readouterr().out.strip() == "192.0.2.30,1,198.51.100.5"


def test_missing_file(tmp_path, capsys):
    assert main(["unsw-nb15", str(tmp_path / "none.csv")]) == 2
