import os
import pytest
from infrastructure.config import Config

class TestConfigDefaults:

    def test_default_user_agent(self, monkeypatch):
        monkeypatch.delenv('REQUEST_TIMEOUT', raising=False)
        monkeypatch.delenv('RATE_LIMIT_DELAY', raising=False)
        monkeypatch.delenv('MAX_RETRIES', raising=False)
        monkeypatch.delenv('DATABASE_URL', raising=False)

        config = Config()
        assert config.USER_AGENT.startswith("Mozilla/5.0")
        assert "Chrome" in config.USER_AGENT

    def test_default_request_timeout(self, monkeypatch):
        monkeypatch.delenv('REQUEST_TIMEOUT', raising=False)
        config = Config()
        assert config.REQUEST_TIMEOUT == 15

    def test_default_rate_limit_delay(self, monkeypatch):
        monkeypatch.delenv('RATE_LIMIT_DELAY', raising=False)
        config = Config()
        assert config.RATE_LIMIT_DELAY == 2.0

    def test_default_max_retries(self, monkeypatch):
        monkeypatch.delenv('MAX_RETRIES', raising=False)
        config = Config()
        assert config.MAX_RETRIES == 2

    def test_default_database_url(self, monkeypatch):
        monkeypatch.delenv('DATABASE_URL', raising=False)
        config = Config()
        assert config.DATABASE_URL == ''

class TestConfigEnvironmentOverride:

    def test_request_timeout_override(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', '30')
        config = Config()
        assert config.REQUEST_TIMEOUT == 30

    def test_rate_limit_delay_override(self, monkeypatch):
        monkeypatch.setenv('RATE_LIMIT_DELAY', '5.0')
        config = Config()
        assert config.RATE_LIMIT_DELAY == 5.0

    def test_max_retries_override(self, monkeypatch):
        monkeypatch.setenv('MAX_RETRIES', '5')
        config = Config()
        assert config.MAX_RETRIES == 5

    def test_database_url_override(self, monkeypatch):
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        config = Config()
        assert config.DATABASE_URL == 'postgresql://localhost/test'

    def test_multiple_overrides(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', '25')
        monkeypatch.setenv('RATE_LIMIT_DELAY', '3.5')
        monkeypatch.setenv('MAX_RETRIES', '4')
        monkeypatch.setenv('DATABASE_URL', 'postgresql://prod/db')

        config = Config()
        assert config.REQUEST_TIMEOUT == 25
        assert config.RATE_LIMIT_DELAY == 3.5
        assert config.MAX_RETRIES == 4
        assert config.DATABASE_URL == 'postgresql://prod/db'

class TestConfigValidation:

    def test_request_timeout_zero_raises_error(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', '0')
        with pytest.raises(ValueError, match="REQUEST_TIMEOUT must be > 0"):
            Config()

    def test_request_timeout_negative_raises_error(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', '-5')
        with pytest.raises(ValueError, match="REQUEST_TIMEOUT must be > 0"):
            Config()

    def test_rate_limit_delay_negative_raises_error(self, monkeypatch):
        monkeypatch.setenv('RATE_LIMIT_DELAY', '-1.0')
        with pytest.raises(ValueError, match="RATE_LIMIT_DELAY must be >= 0"):
            Config()

    def test_rate_limit_delay_zero_is_valid(self, monkeypatch):
        monkeypatch.setenv('RATE_LIMIT_DELAY', '0')
        config = Config()
        assert config.RATE_LIMIT_DELAY == 0.0

    def test_max_retries_negative_raises_error(self, monkeypatch):
        monkeypatch.setenv('MAX_RETRIES', '-1')
        with pytest.raises(ValueError, match="MAX_RETRIES must be >= 0"):
            Config()

    def test_max_retries_zero_is_valid(self, monkeypatch):
        monkeypatch.setenv('MAX_RETRIES', '0')
        config = Config()
        assert config.MAX_RETRIES == 0

class TestConfigImmutability:

    def test_cannot_modify_request_timeout(self, monkeypatch):
        monkeypatch.delenv('REQUEST_TIMEOUT', raising=False)
        config = Config()

        with pytest.raises(AttributeError):
            config.REQUEST_TIMEOUT = 999

    def test_cannot_modify_rate_limit_delay(self, monkeypatch):
        monkeypatch.delenv('RATE_LIMIT_DELAY', raising=False)
        config = Config()

        with pytest.raises(AttributeError):
            config.RATE_LIMIT_DELAY = 999.0

    def test_cannot_modify_max_retries(self, monkeypatch):
        monkeypatch.delenv('MAX_RETRIES', raising=False)
        config = Config()

        with pytest.raises(AttributeError):
            config.MAX_RETRIES = 999

    def test_cannot_modify_database_url(self, monkeypatch):
        monkeypatch.delenv('DATABASE_URL', raising=False)
        config = Config()

        with pytest.raises(AttributeError):
            config.DATABASE_URL = 'postgresql://hacked/db'

    def test_cannot_modify_user_agent(self, monkeypatch):
        monkeypatch.delenv('REQUEST_TIMEOUT', raising=False)
        config = Config()

        with pytest.raises(AttributeError):
            config.USER_AGENT = 'BadBot/1.0'

class TestConfigInvalidEnvironmentValues:

    def test_invalid_request_timeout_non_numeric(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', 'not-a-number')
        with pytest.raises(ValueError):
            Config()

    def test_invalid_rate_limit_delay_non_numeric(self, monkeypatch):
        monkeypatch.setenv('RATE_LIMIT_DELAY', 'not-a-number')
        with pytest.raises(ValueError):
            Config()

    def test_invalid_max_retries_non_numeric(self, monkeypatch):
        monkeypatch.setenv('MAX_RETRIES', 'not-a-number')
        with pytest.raises(ValueError):
            Config()
