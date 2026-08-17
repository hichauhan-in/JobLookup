from __future__ import annotations

import pytest

from joblookup.llm.base import LLMError, extract_json


class TestExtractJson:
    def test_plain(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}

    def test_surrounded_by_prose(self):
        assert extract_json('Sure! {"a": 1} Hope that helps.') == {"a": 1}

    def test_trailing_comma_is_repaired(self):
        assert extract_json('{"a": 1,}') == {"a": 1}

    def test_braces_inside_strings_do_not_confuse_it(self):
        assert extract_json('{"note": "use {curly} braces"}') == {"note": "use {curly} braces"}

    def test_array(self):
        assert extract_json("[1, 2, 3]") == [1, 2, 3]

    def test_failure_quotes_what_the_model_said(self):
        # Without the quote, "did not return JSON" is unactionable.
        with pytest.raises(LLMError) as error:
            extract_json("I need the job descriptions first.")
        assert "I need the job descriptions" in str(error.value)
