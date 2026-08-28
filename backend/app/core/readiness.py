from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReadinessResult:
    database_ok: bool
    schema_ok: bool

    @property
    def ready(self) -> bool:
        return self.database_ok and self.schema_ok


class ReadinessService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def check(self) -> ReadinessResult:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                current_revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
        except Exception:
            return ReadinessResult(database_ok=False, schema_ok=False)

        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        expected_heads = set(ScriptDirectory.from_config(config).get_heads())
        return ReadinessResult(
            database_ok=True,
            schema_ok=current_revision is not None and {current_revision} == expected_heads,
        )
