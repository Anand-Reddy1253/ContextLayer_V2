from context_fabric.settings import Settings


def test_settings_defaults_carry_no_real_secret(monkeypatch, tmp_path):
    # Isolate from any real .env / real environment secrets that might be
    # set on the developer's machine.
    monkeypatch.chdir(tmp_path)
    for key in (
        "CF_SECRET_KEY",
        "CF_ADO_PAT",
        "CF_GITHUB_TOKEN",
        "CF_GITHUB_APP_PRIVATE_KEY_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.CF_MODE == "fixture"
    assert settings.CF_SECRET_KEY is None
    assert settings.CF_ADO_PAT is None
    assert settings.CF_GITHUB_TOKEN is None
    assert settings.CF_API_PORT == 8000


def test_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("CF_MODE", "live")
    monkeypatch.setenv("CF_API_PORT", "9000")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.CF_MODE == "live"
    assert settings.CF_API_PORT == 9000
