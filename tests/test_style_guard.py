from __future__ import annotations

from joblookup.tailor import style_guard


class TestTypography:
    def test_em_dash_becomes_a_hyphen(self):
        # The single most recognisable tell, because almost nobody types one.
        assert "—" not in style_guard.clean("Led the migration—on time and under budget.")

    def test_en_dash_too(self):
        assert "–" not in style_guard.clean("2019–2024")

    def test_smart_quotes_and_ellipsis(self):
        result = style_guard.clean("\u201cDone\u201d\u2026")
        assert result == '"Done"...'


class TestVocabulary:
    def test_replaces_banned_words(self):
        result = style_guard.clean("Leveraged Kubernetes to deliver a robust, seamless platform.")
        lowered = result.lower()
        assert "leverage" not in lowered
        assert "robust" not in lowered
        assert "seamless" not in lowered
        assert "Kubernetes" in result

    def test_preserves_capitalisation(self):
        assert style_guard.clean("Utilise the API").startswith("Use")

    def test_flags_what_it_will_not_rewrite(self):
        report = style_guard.GuardReport()
        style_guard.clean("A rich tapestry of transformative work.", report)
        assert "tapestry" in report.flagged


class TestPatterns:
    def test_removes_not_just_x_but_y(self):
        result = style_guard.clean("It's not just a job, it is a mission to improve reliability.")
        assert "not just" not in result.lower()
        assert "reliability" in result

    def test_strips_emoji(self):
        assert "🚀" not in style_guard.clean("Shipped it 🚀")


class TestDocument:
    def test_walks_nested_structures(self):
        content = {
            "summary": "Leveraged a robust pipeline",
            "roles": [{"bullets": ["Spearheaded delivery—on time"]}],
            "count": 3,
        }
        cleaned, report = style_guard.apply(content)
        assert "leveraged" not in cleaned["summary"].lower()
        assert "—" not in cleaned["roles"][0]["bullets"][0]
        assert cleaned["count"] == 3
        assert report.changes >= 2

    def test_leaves_clean_writing_alone(self):
        original = "Ran the on-call rotation for a team of eight."
        report = style_guard.GuardReport()
        assert style_guard.clean(original, report) == original
        assert report.changes == 0
