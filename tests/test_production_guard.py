import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


CONFIG_ENV_VARS = ("ADMIN_SESSION_SECRET", "ENVIRONMENT")


def _run(code: str, db_path: Path, **env) -> subprocess.CompletedProcess:
    base_env = {k: v for k, v in os.environ.items() if k not in CONFIG_ENV_VARS}
    full_env = {**base_env, "DATABASE_URL": f"sqlite:///{db_path}", **env}
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=full_env, capture_output=True, text=True)


def test_production_refuses_default_session_secret(tmp_path):
    result = _run("import main", tmp_path / "t.db", ENVIRONMENT="production")
    assert result.returncode != 0
    assert "ADMIN_SESSION_SECRET" in result.stderr


def test_production_hides_api_docs_when_secret_is_set(tmp_path):
    code = (
        "from fastapi.testclient import TestClient; import main\n"
        "with TestClient(main.app) as c:\n"
        "    assert c.get('/docs').status_code == 404\n"
        "    assert c.get('/openapi.json').status_code == 404\n"
        "    assert c.get('/health').status_code == 200\n"
    )
    result = _run(code, tmp_path / "t.db", ENVIRONMENT="production", ADMIN_SESSION_SECRET="x" * 40)
    assert result.returncode == 0, result.stderr


def test_development_keeps_api_docs(tmp_path):
    code = (
        "from fastapi.testclient import TestClient; import main\n"
        "with TestClient(main.app) as c:\n"
        "    assert c.get('/docs').status_code == 200\n"
    )
    result = _run(code, tmp_path / "t.db", ENVIRONMENT="development")
    assert result.returncode == 0, result.stderr


def test_env_example_loads_without_validation_errors(tmp_path):
    """Регрессия: .env.example содержит POSTGRES_USER/PASSWORD/DB для
    docker-compose.yml, которых нет как полей Settings — без
    model_config(extra="ignore") copy .env.example -> .env валит приложение
    на старте (см. config.py)."""
    env_file = tmp_path / ".env"
    shutil.copy(ROOT / ".env.example", env_file)

    result = _run(
        "from config import Settings; s = Settings(_env_file=%r); print(s.company_name)" % str(env_file),
        tmp_path / "t.db",
    )
    assert result.returncode == 0, result.stderr
    assert "OknoPro" in result.stdout
