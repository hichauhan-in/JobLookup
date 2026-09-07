from types import SimpleNamespace

import pytest

from joblookup.config import Settings
from joblookup.sources.tier_b import browser


def test_empty_browser_profile_does_not_mean_signed_in(tmp_path):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    directory = browser.profile_dir(settings, "linkedin")
    (directory / "Default").mkdir()
    (directory / "Preferences").write_text("{}", encoding="utf-8")

    assert browser.has_session(settings, "linkedin") is False


def test_checking_session_does_not_create_a_profile(tmp_path):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)

    assert browser.has_session(settings, "linkedin") is False
    assert not (tmp_path / "browser_profiles").exists()


def test_only_a_confirmed_session_is_ready(tmp_path):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    browser.record_session(settings, "linkedin", authenticated=True)
    assert browser.has_session(settings, "linkedin") is True
    browser.record_session(settings, "linkedin", authenticated=False)
    assert browser.has_session(settings, "linkedin") is False


def test_corrupt_session_marker_is_not_signed_in(tmp_path):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    marker = browser.profile_dir(settings, "linkedin") / ".session.json"
    marker.write_text("broken", encoding="utf-8")
    assert browser.has_session(settings, "linkedin") is False


def stub_browser(monkeypatch, *, navigation_error=False):
    closed = []
    callbacks = {}

    def goto(*args, **kwargs):
        if navigation_error:
            raise RuntimeError("Navigation failed")

    page = SimpleNamespace(goto=goto, is_closed=lambda: False, wait_for_timeout=lambda _: None)
    context = SimpleNamespace(
        pages=[page],
        on=lambda event, handler: callbacks.update({event: handler}),
        close=lambda: closed.append(True),
    )
    playwright = SimpleNamespace(stop=lambda: None)
    monkeypatch.setattr(browser, "launch_context", lambda *args, **kwargs: (playwright, context))
    return closed


def test_sign_in_requires_a_positive_authentication_signal(tmp_path, monkeypatch):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    closed = stub_browser(monkeypatch)
    result = browser.sign_in(
        settings, "linkedin", "https://www.linkedin.com/login", authenticated=lambda *args: True
    )
    assert result["session_saved"] is True
    assert browser.has_session(settings, "linkedin")
    assert closed


def test_failed_navigation_is_not_a_successful_sign_in(tmp_path, monkeypatch):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    stub_browser(monkeypatch, navigation_error=True)
    with pytest.raises(browser.TierBBlocked, match="could not be completed"):
        browser.sign_in(
            settings,
            "linkedin",
            "https://www.linkedin.com/login",
            authenticated=lambda *args: False,
        )
    assert not browser.has_session(settings, "linkedin")


def test_sign_in_can_be_cancelled(tmp_path, monkeypatch):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    stub_browser(monkeypatch)
    result = browser.sign_in(
        settings,
        "linkedin",
        "https://www.linkedin.com/login",
        authenticated=lambda *args: False,
        cancelled=lambda: True,
    )
    assert result["session_saved"] is False
    assert result["detail"] == "Sign-in cancelled."


def test_sign_in_times_out_without_saving_an_unverified_session(tmp_path, monkeypatch):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    stub_browser(monkeypatch)
    result = browser.sign_in(
        settings,
        "linkedin",
        "https://www.linkedin.com/login",
        authenticated=lambda *args: False,
        timeout_s=0,
    )
    assert result["session_saved"] is False
    assert "timed out" in result["detail"]


def test_session_operations_cannot_overlap(tmp_path):
    settings = Settings()
    settings.paths.workspace = str(tmp_path)
    with (
        browser.session_access(settings, "linkedin"),
        pytest.raises(browser.TierBBlocked, match="another browser operation"),
    ):
        browser.clear_session(settings, "linkedin")


def test_linkedin_authentication_requires_its_own_host_and_auth_cookie():
    from joblookup.sources import registry

    adapter = registry.get_adapter("linkedin")
    page = SimpleNamespace(
        url="https://www.linkedin.com/feed/",
        locator=lambda _: SimpleNamespace(first=SimpleNamespace(is_visible=lambda: False)),
    )
    context = SimpleNamespace(cookies=lambda urls: [{"name": "li_at", "value": "test-cookie"}])
    assert adapter.authenticated(page, context) is True
    page.url = "https://www.linkedin.com/checkpoint/challenge"
    assert adapter.authenticated(page, context) is False
    page.url = "https://attacker.test/feed/"
    assert adapter.authenticated(page, context) is False
    page.url = "https://www.linkedin.com/feed/"
    context.cookies = lambda urls: [{"name": "visitor", "value": "not-authentication"}]
    assert adapter.authenticated(page, context) is False
