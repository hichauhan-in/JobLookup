from __future__ import annotations

import pytest
import yaml

from joblookup import config as config_module


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "default.yaml").write_text(
        yaml.safe_dump({"search": {"recency_days": 7}, "matching": {"prefilter_keep": 120}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOBLOOKUP_HOME", str(tmp_path))
    return tmp_path


def test_defaults_load(workspace):
    settings = config_module.load_settings()
    assert settings.search.recency_days == 7
    assert settings.matching.prefilter_keep == 120


def test_local_overrides_win(workspace):
    (workspace / "config" / "local.yaml").write_text(
        yaml.safe_dump({"search": {"recency_days": 21}}), encoding="utf-8"
    )
    assert config_module.load_settings().search.recency_days == 21


def test_environment_beats_the_file(workspace, monkeypatch):
    monkeypatch.setenv("JOBLOOKUP_SEARCH_RECENCY_DAYS", "3")
    assert config_module.load_settings().search.recency_days == 3


def test_environment_reaches_nested_sections(workspace, monkeypatch):
    monkeypatch.setenv("JOBLOOKUP_LLM_VSCODE_MODEL", "gpt-4o-mini")
    assert config_module.load_settings().llm.vscode.model == "gpt-4o-mini"


def test_booleans_are_coerced(workspace, monkeypatch):
    monkeypatch.setenv("JOBLOOKUP_TIER_B_ENABLED", "true")
    assert config_module.load_settings().tier_b.enabled is True


def test_saving_writes_only_the_difference(workspace):
    config_module.save_local_overrides({"matching": {"score_batch_size": 4}})
    written = yaml.safe_load((workspace / "config" / "local.yaml").read_text(encoding="utf-8"))
    assert written == {"matching": {"score_batch_size": 4}}
    assert config_module.load_settings().matching.score_batch_size == 4


def test_a_bad_value_is_rejected_before_it_is_written(workspace):
    # pydantic's ValidationError is a ValueError, which is what a caller would catch.
    with pytest.raises(ValueError):
        config_module.save_local_overrides({"matching": {"recall_mode": "telepathy"}})
    assert not (workspace / "config" / "local.yaml").exists()
