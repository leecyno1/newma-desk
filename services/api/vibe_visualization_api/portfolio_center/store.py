from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from vibe_visualization_api.portfolio_center.models import (
    LegacyImportResult,
    PortfolioAccount,
    PortfolioAccountCreate,
    PortfolioActivity,
    PortfolioActivityCreate,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_accounts (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  currency TEXT NOT NULL,
  platform TEXT,
  account_type TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id)
);

CREATE TABLE IF NOT EXISTS portfolio_activities (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  type TEXT NOT NULL,
  market TEXT,
  symbol TEXT,
  name TEXT,
  currency TEXT NOT NULL,
  quantity REAL,
  unit_price REAL,
  amount REAL,
  fee REAL NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id),
  FOREIGN KEY (user_id, workspace_id, account_id)
    REFERENCES portfolio_accounts(user_id, workspace_id, id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS portfolio_activity_scope_time
ON portfolio_activities(user_id, workspace_id, occurred_at, id);

CREATE TABLE IF NOT EXISTS portfolio_migrations (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  migration_id TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, migration_id)
);
"""


class PortfolioConflictError(Exception):
    """Raised when a portfolio mutation conflicts with current ledger state."""


class PortfolioNotFoundError(Exception):
    """Raised when an account or activity is unavailable."""


class PortfolioStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _account(row: sqlite3.Row) -> PortfolioAccount:
        return PortfolioAccount.model_validate(
            {
                "id": row["id"],
                "name": row["name"],
                "currency": row["currency"],
                "platform": row["platform"],
                "accountType": row["account_type"],
                "archived": bool(row["archived"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
        )

    @staticmethod
    def _activity(row: sqlite3.Row) -> PortfolioActivity:
        return PortfolioActivity.model_validate(
            {
                "id": row["id"],
                "accountId": row["account_id"],
                "type": row["type"],
                "market": row["market"],
                "symbol": row["symbol"],
                "name": row["name"],
                "currency": row["currency"],
                "quantity": row["quantity"],
                "unitPrice": row["unit_price"],
                "amount": row["amount"],
                "fee": row["fee"],
                "occurredAt": row["occurred_at"],
                "note": row["note"],
                "source": row["source"],
                "createdAt": row["created_at"],
            }
        )

    def list_accounts(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> list[PortfolioAccount]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT * FROM portfolio_accounts
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY archived, created_at, id
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [self._account(row) for row in rows]

    def create_account(
        self,
        *,
        user_id: str,
        workspace_id: str,
        account: PortfolioAccountCreate,
    ) -> PortfolioAccount:
        now = self._now()
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            try:
                connection.execute(
                    """
                    INSERT INTO portfolio_accounts (
                      user_id, workspace_id, id, name, currency, platform,
                      account_type, archived, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        user_id,
                        workspace_id,
                        account.id,
                        account.name,
                        account.currency,
                        account.platform,
                        account.account_type,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise PortfolioConflictError("portfolio account already exists") from error
            row = connection.execute(
                """
                SELECT * FROM portfolio_accounts
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, account.id),
            ).fetchone()
        assert row is not None
        return self._account(row)

    def ensure_default_account(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> PortfolioAccount:
        accounts = self.list_accounts(user_id=user_id, workspace_id=workspace_id)
        if accounts:
            return accounts[0]
        try:
            return self.create_account(
                user_id=user_id,
                workspace_id=workspace_id,
                account=PortfolioAccountCreate(
                    id="main",
                    name="主账户",
                    currency="CNY",
                    platform="Newma-Desk",
                ),
            )
        except PortfolioConflictError:
            return self.list_accounts(
                user_id=user_id,
                workspace_id=workspace_id,
            )[0]

    def list_activities(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int = 2_000,
    ) -> list[PortfolioActivity]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                """
                SELECT * FROM portfolio_activities
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY occurred_at, created_at, id
                LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
        return [self._activity(row) for row in rows]

    def add_activity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        activity: PortfolioActivityCreate,
        activity_id: str | None = None,
    ) -> PortfolioActivity:
        identifier = activity_id or str(uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            account = connection.execute(
                """
                SELECT 1 FROM portfolio_accounts
                WHERE user_id = ? AND workspace_id = ? AND id = ? AND archived = 0
                """,
                (user_id, workspace_id, activity.account_id),
            ).fetchone()
            if account is None:
                raise PortfolioNotFoundError("portfolio account was not found")
            try:
                connection.execute(
                    """
                    INSERT INTO portfolio_activities (
                      user_id, workspace_id, id, account_id, type, market,
                      symbol, name, currency, quantity, unit_price, amount,
                      fee, occurred_at, note, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        workspace_id,
                        identifier,
                        activity.account_id,
                        activity.type,
                        activity.market,
                        activity.symbol,
                        activity.name,
                        activity.currency,
                        activity.quantity,
                        activity.unit_price,
                        activity.amount,
                        activity.fee,
                        activity.occurred_at.isoformat(),
                        activity.note,
                        activity.source,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise PortfolioConflictError("portfolio activity already exists") from error
            row = connection.execute(
                """
                SELECT * FROM portfolio_activities
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, identifier),
            ).fetchone()
        assert row is not None
        return self._activity(row)

    def delete_activity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        activity_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            cursor = connection.execute(
                """
                DELETE FROM portfolio_activities
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, activity_id),
            )
            if cursor.rowcount == 0:
                raise PortfolioNotFoundError("portfolio activity was not found")

    def import_legacy_document(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict,
        migration_id: str = "vibe-research-portfolio-json-v1",
    ) -> LegacyImportResult:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            applied = connection.execute(
                """
                SELECT 1 FROM portfolio_migrations
                WHERE user_id = ? AND workspace_id = ? AND migration_id = ?
                """,
                (user_id, workspace_id, migration_id),
            ).fetchone()
            if applied is not None:
                return LegacyImportResult(
                    imported=False,
                    activities_created=0,
                    reason="already-imported",
                )

        account = self.ensure_default_account(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        created = 0
        imported_at = datetime.now(UTC)
        holdings = document.get("holdings") if isinstance(document, dict) else None
        if isinstance(holdings, list):
            for index, raw in enumerate(holdings):
                if not isinstance(raw, dict):
                    continue
                try:
                    code = str(raw["code"]).strip()
                    activity = PortfolioActivityCreate(
                        accountId=account.id,
                        type="buy",
                        market="CN",
                        symbol=code,
                        name=str(raw.get("name") or code),
                        currency="CNY",
                        quantity=float(raw["shares"]),
                        unitPrice=float(raw["cost"]),
                        occurredAt=imported_at,
                        note="从 Vibe-Research 旧持仓导入",
                        source="import",
                    )
                    self.add_activity(
                        user_id=user_id,
                        workspace_id=workspace_id,
                        activity=activity,
                        activity_id=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"{migration_id}:holding:{index}:{code}",
                            )
                        ),
                    )
                    created += 1
                except (KeyError, TypeError, ValueError, PortfolioConflictError):
                    continue

        closed = document.get("closed") if isinstance(document, dict) else None
        if isinstance(closed, list):
            for index, raw in enumerate(closed):
                if not isinstance(raw, dict):
                    continue
                try:
                    code = str(raw["code"]).strip()
                    occurred_at = datetime.fromisoformat(str(raw["date"]))
                    if occurred_at.tzinfo is None:
                        occurred_at = occurred_at.replace(tzinfo=UTC)
                    common = {
                        "accountId": account.id,
                        "market": "CN",
                        "symbol": code,
                        "name": str(raw.get("name") or code),
                        "currency": "CNY",
                        "quantity": float(raw["shares"]),
                        "occurredAt": occurred_at,
                        "note": "从 Vibe-Research 旧清仓记录导入",
                        "source": "import",
                    }
                    for activity_type, price in (
                        ("buy", float(raw["cost"])),
                        ("sell", float(raw["price"])),
                    ):
                        self.add_activity(
                            user_id=user_id,
                            workspace_id=workspace_id,
                            activity=PortfolioActivityCreate(
                                **common,
                                type=activity_type,
                                unitPrice=price,
                            ),
                            activity_id=str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"{migration_id}:closed:{index}:{code}:{activity_type}",
                                )
                            ),
                        )
                        created += 1
                except (KeyError, TypeError, ValueError, PortfolioConflictError):
                    continue

        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO portfolio_migrations (
                  user_id, workspace_id, migration_id, applied_at
                ) VALUES (?, ?, ?, ?)
                """,
                (user_id, workspace_id, migration_id, self._now()),
            )
        return LegacyImportResult(
            imported=True,
            activities_created=created,
            reason="imported",
        )

    def import_legacy_file(
        self,
        *,
        user_id: str,
        workspace_id: str,
        path: Path,
    ) -> LegacyImportResult:
        try:
            document = json.loads(path.expanduser().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return LegacyImportResult(
                imported=False,
                activities_created=0,
                reason="file-not-found",
            )
        except (OSError, json.JSONDecodeError):
            return LegacyImportResult(
                imported=False,
                activities_created=0,
                reason="invalid-file",
            )
        if not isinstance(document, dict):
            return LegacyImportResult(
                imported=False,
                activities_created=0,
                reason="invalid-document",
            )
        return self.import_legacy_document(
            user_id=user_id,
            workspace_id=workspace_id,
            document=document,
        )
