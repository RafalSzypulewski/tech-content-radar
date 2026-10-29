from radar.config import Settings, load_settings, load_sources

SOURCES_YAML = """
defaults: {trust: 0.5, max_age_days: 21}
sources:
  - {id: a, name: A, kind: rss, type: blog, url: "https://a.example.com"}
  - {id: b, name: B, kind: rss, type: blog, url: "https://b.example.com", trust: 0.9, lang: pl}
"""


def test_load_sources_merges_defaults(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(SOURCES_YAML, encoding="utf-8")

    a, b = load_sources(path)

    assert (a.trust, a.max_age_days, a.lang) == (0.5, 21, "en")
    assert (b.trust, b.max_age_days, b.lang) == (0.9, 21, "pl")


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MAX_ITEMS", raising=False)
    monkeypatch.delenv("FRESHNESS_HALF_LIFE_DAYS", raising=False)
    assert load_settings(env_file=None) == Settings(60, 7.0)


def test_settings_from_env_file_and_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MAX_ITEMS", "")  # registers cleanup of what load_dotenv writes
    monkeypatch.delenv("LLM_MAX_ITEMS")
    monkeypatch.setenv("FRESHNESS_HALF_LIFE_DAYS", "3.5")
    env = tmp_path / ".env"
    env.write_text("LLM_MAX_ITEMS=10\n", encoding="utf-8")

    assert load_settings(env) == Settings(10, 3.5)
