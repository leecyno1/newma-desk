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
    PortfolioOrder,
    PortfolioOrderCreate,
    PortfolioOrderUpdate,
    PortfolioRiskAction,
    PortfolioRiskActionCreate,
    PortfolioRiskActionUpdate,
    PortfolioRiskPolicy,
    PortfolioRiskPolicyInput,
    PortfolioRiskReport,
    PortfolioDashboard,
    PortfolioPerformanceResult,
    PortfolioPerformanceRequest,
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
  order_id TEXT,
  execution_id TEXT,
  settlement_date TEXT,
  decision_price REAL,
  arrival_price REAL,
  benchmark_price REAL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id),
  FOREIGN KEY (user_id, workspace_id, account_id)
    REFERENCES portfolio_accounts(user_id, workspace_id, id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS portfolio_activity_scope_time
ON portfolio_activities(user_id, workspace_id, occurred_at, id);

CREATE TABLE IF NOT EXISTS portfolio_orders (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  side TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  currency TEXT NOT NULL,
  order_type TEXT NOT NULL,
  quantity REAL NOT NULL,
  limit_price REAL,
  stop_price REAL,
  time_in_force TEXT NOT NULL,
  status TEXT NOT NULL,
  filled_quantity REAL NOT NULL DEFAULT 0,
  average_fill_price REAL,
  submitted_at TEXT,
  expires_at TEXT,
  broker_order_id TEXT,
  note TEXT,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id),
  FOREIGN KEY (user_id, workspace_id, account_id)
    REFERENCES portfolio_accounts(user_id, workspace_id, id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS portfolio_order_scope_time
ON portfolio_orders(user_id, workspace_id, created_at, id);

CREATE TABLE IF NOT EXISTS portfolio_risk_policy (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  single_position_limit_pct REAL NOT NULL,
  top_three_limit_pct REAL NOT NULL,
  min_effective_positions REAL NOT NULL,
  max_drawdown_limit_pct REAL NOT NULL,
  var95_limit_pct REAL NOT NULL,
  max_unpriced_positions INTEGER NOT NULL,
  allow_negative_cash INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS portfolio_risk_actions (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  owner TEXT,
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  resolved_at TEXT,
  PRIMARY KEY (user_id, workspace_id, id)
);

CREATE INDEX IF NOT EXISTS portfolio_risk_action_scope_time
ON portfolio_risk_actions(user_id, workspace_id, updated_at, id);

CREATE TABLE IF NOT EXISTS portfolio_risk_reports (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  saved_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id)
);

CREATE TABLE IF NOT EXISTS portfolio_migrations (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  migration_id TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, migration_id)
);

CREATE TABLE IF NOT EXISTS portfolio_import_snapshots (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  id TEXT NOT NULL,
  saved_at TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  report TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id, id)
);
"""


class PortfolioConflictError(Exception):
    """Raised when a portfolio mutation conflicts with current ledger state."""


class PortfolioNotFoundError(Exception):
    """Raised when an account or activity is unavailable."""


class PortfolioStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def save_import_snapshot(self, *, user_id: str, workspace_id: str, snapshot: dict, report: dict) -> dict:
        serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT * FROM portfolio_import_snapshots WHERE user_id=? AND workspace_id=? AND snapshot=? ORDER BY saved_at DESC LIMIT 1', (user_id, workspace_id, serialized)).fetchone()
            if existing and json.loads(existing['report']) == report:
                return self._import_snapshot(existing)
            snapshot_id, saved_at = str(uuid4()), datetime.now(UTC).isoformat()
            connection.execute('INSERT INTO portfolio_import_snapshots VALUES (?,?,?,?,?,?)', (user_id, workspace_id, snapshot_id, saved_at, serialized, json.dumps(report, ensure_ascii=False)))
        return {"id": snapshot_id, "savedAt": saved_at, "snapshot": snapshot, "report": report}

    @staticmethod
    def _import_snapshot(row) -> dict:
        return {"id": row['id'], "savedAt": row['saved_at'], "snapshot": json.loads(row['snapshot']), "report": json.loads(row['report'])}

    def list_import_snapshots(self, *, user_id: str, workspace_id: str) -> list[dict]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute('SELECT * FROM portfolio_import_snapshots WHERE user_id=? AND workspace_id=? ORDER BY saved_at DESC LIMIT 50', (user_id, workspace_id)).fetchall()
        return [self._import_snapshot(row) for row in rows]

    def get_import_snapshot(self, *, user_id: str, workspace_id: str, snapshot_id: str) -> dict:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute('SELECT * FROM portfolio_import_snapshots WHERE user_id=? AND workspace_id=? AND id=?', (user_id, workspace_id, snapshot_id)).fetchone()
        if row is None:
            raise PortfolioNotFoundError('组合快照不存在')
        return self._import_snapshot(row)

    def list_import_products(self, *, user_id: str, workspace_id: str) -> list[dict]:
        """One latest-dated snapshot per explicit product; never net products together."""
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute('''
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY json_extract(snapshot, '$.productId')
                        ORDER BY json_extract(snapshot, '$.asOf') DESC, saved_at DESC, id DESC
                    ) AS product_rank
                    FROM portfolio_import_snapshots
                    WHERE user_id=? AND workspace_id=?
                      AND COALESCE(json_extract(snapshot, '$.productId'), '') <> ''
                ) WHERE product_rank=1
                ORDER BY json_extract(snapshot, '$.productId')
            ''', (user_id, workspace_id)).fetchall()
        return [self._import_snapshot(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _prepare(connection: sqlite3.Connection) -> None:
        connection.executescript(SCHEMA)
        risk_columns = {row['name'] for row in connection.execute('PRAGMA table_info(portfolio_risk_actions)')}
        if 'due_at' not in risk_columns:
            connection.execute('ALTER TABLE portfolio_risk_actions ADD COLUMN due_at TEXT')
        if 'source_snapshot_id' not in risk_columns:
            connection.execute('ALTER TABLE portfolio_risk_actions ADD COLUMN source_snapshot_id TEXT')
        if 'review_snapshot_id' not in risk_columns:
            connection.execute('ALTER TABLE portfolio_risk_actions ADD COLUMN review_snapshot_id TEXT')
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(portfolio_activities)")
        }
        additions = {
            "order_id": "TEXT",
            "execution_id": "TEXT",
            "settlement_date": "TEXT",
            "decision_price": "REAL",
            "arrival_price": "REAL",
            "benchmark_price": "REAL",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE portfolio_activities ADD COLUMN {name} {definition}"
                )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS portfolio_activity_order
            ON portfolio_activities(user_id, workspace_id, order_id)
            """
        )

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
                "orderId": row["order_id"],
                "executionId": row["execution_id"],
                "settlementDate": row["settlement_date"],
                "decisionPrice": row["decision_price"],
                "arrivalPrice": row["arrival_price"],
                "benchmarkPrice": row["benchmark_price"],
                "createdAt": row["created_at"],
            }
        )

    @staticmethod
    def _order(row: sqlite3.Row) -> PortfolioOrder:
        return PortfolioOrder.model_validate(
            {
                "id": row["id"],
                "accountId": row["account_id"],
                "side": row["side"],
                "market": row["market"],
                "symbol": row["symbol"],
                "name": row["name"],
                "currency": row["currency"],
                "orderType": row["order_type"],
                "quantity": row["quantity"],
                "limitPrice": row["limit_price"],
                "stopPrice": row["stop_price"],
                "timeInForce": row["time_in_force"],
                "status": row["status"],
                "filledQuantity": row["filled_quantity"],
                "averageFillPrice": row["average_fill_price"],
                "submittedAt": row["submitted_at"],
                "expiresAt": row["expires_at"],
                "brokerOrderId": row["broker_order_id"],
                "note": row["note"],
                "source": row["source"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
        )

    @staticmethod
    def _risk_policy(row: sqlite3.Row) -> PortfolioRiskPolicy:
        return PortfolioRiskPolicy.model_validate(
            {
                "singlePositionLimitPct": row["single_position_limit_pct"],
                "topThreeLimitPct": row["top_three_limit_pct"],
                "minEffectivePositions": row["min_effective_positions"],
                "maxDrawdownLimitPct": row["max_drawdown_limit_pct"],
                "var95LimitPct": row["var95_limit_pct"],
                "maxUnpricedPositions": row["max_unpriced_positions"],
                "allowNegativeCash": bool(row["allow_negative_cash"]),
                "updatedAt": row["updated_at"],
            }
        )

    @staticmethod
    def _risk_action(row: sqlite3.Row) -> PortfolioRiskAction:
        return PortfolioRiskAction.model_validate(
            {
                "id": row["id"],
                "ruleId": row["rule_id"],
                "sourceSnapshotId": row['source_snapshot_id'],
                "reviewSnapshotId": row['review_snapshot_id'],
                "severity": row["severity"],
                "status": row["status"],
                "title": row["title"],
                "detail": row["detail"],
                "owner": row["owner"],
                "note": row["note"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "resolvedAt": row["resolved_at"],
                "dueAt": row["due_at"],
            }
        )

    def list_accounts(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> list[PortfolioAccount]:
        with self._connect() as connection:
            self._prepare(connection)
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
            self._prepare(connection)
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

    def list_orders(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int = 1_000,
    ) -> list[PortfolioOrder]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM portfolio_orders
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, workspace_id, limit),
            ).fetchall()
        return [self._order(row) for row in rows]

    def get_order(
        self,
        *,
        user_id: str,
        workspace_id: str,
        order_id: str,
    ) -> PortfolioOrder:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM portfolio_orders
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, order_id),
            ).fetchone()
        if row is None:
            raise PortfolioNotFoundError("portfolio order was not found")
        return self._order(row)

    def create_order(
        self,
        *,
        user_id: str,
        workspace_id: str,
        order: PortfolioOrderCreate,
    ) -> PortfolioOrder:
        identifier = str(uuid4())
        now = self._now()
        submitted_at = order.submitted_at
        if order.status == "submitted" and submitted_at is None:
            submitted_at = datetime.now(UTC)
        with self._connect() as connection:
            self._prepare(connection)
            account = connection.execute(
                """
                SELECT 1 FROM portfolio_accounts
                WHERE user_id = ? AND workspace_id = ? AND id = ? AND archived = 0
                """,
                (user_id, workspace_id, order.account_id),
            ).fetchone()
            if account is None:
                raise PortfolioNotFoundError("portfolio account was not found")
            connection.execute(
                """
                INSERT INTO portfolio_orders (
                  user_id, workspace_id, id, account_id, side, market, symbol,
                  name, currency, order_type, quantity, limit_price, stop_price,
                  time_in_force, status, filled_quantity, average_fill_price,
                  submitted_at, expires_at, broker_order_id, note, source,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    identifier,
                    order.account_id,
                    order.side,
                    order.market,
                    order.symbol,
                    order.name,
                    order.currency,
                    order.order_type,
                    order.quantity,
                    order.limit_price,
                    order.stop_price,
                    order.time_in_force,
                    order.status,
                    submitted_at.isoformat() if submitted_at else None,
                    order.expires_at.isoformat() if order.expires_at else None,
                    order.broker_order_id,
                    order.note,
                    order.source,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM portfolio_orders
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, identifier),
            ).fetchone()
        assert row is not None
        return self._order(row)

    def update_order(
        self,
        *,
        user_id: str,
        workspace_id: str,
        order_id: str,
        update: PortfolioOrderUpdate,
    ) -> PortfolioOrder:
        current = self.get_order(
            user_id=user_id,
            workspace_id=workspace_id,
            order_id=order_id,
        )
        fields = update.model_fields_set
        status_value = update.status if "status" in fields else current.status
        filled_quantity = (
            update.filled_quantity
            if "filled_quantity" in fields
            else current.filled_quantity
        )
        average_fill_price = (
            update.average_fill_price
            if "average_fill_price" in fields
            else current.average_fill_price
        )
        broker_order_id = (
            update.broker_order_id
            if "broker_order_id" in fields
            else current.broker_order_id
        )
        note = update.note if "note" in fields else current.note
        now = self._now()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                UPDATE portfolio_orders
                SET status = ?, filled_quantity = ?, average_fill_price = ?,
                    broker_order_id = ?, note = ?, updated_at = ?
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (
                    status_value,
                    filled_quantity,
                    average_fill_price,
                    broker_order_id,
                    note,
                    now,
                    user_id,
                    workspace_id,
                    order_id,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM portfolio_orders
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, order_id),
            ).fetchone()
        assert row is not None
        return self._order(row)

    def list_activities(
        self,
        *,
        user_id: str,
        workspace_id: str,
        limit: int = 2_000,
    ) -> list[PortfolioActivity]:
        with self._connect() as connection:
            self._prepare(connection)
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

    def get_activity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        activity_id: str,
    ) -> PortfolioActivity:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM portfolio_activities
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, activity_id),
            ).fetchone()
        if row is None:
            raise PortfolioNotFoundError("portfolio activity was not found")
        return self._activity(row)

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
            self._prepare(connection)
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
                      fee, occurred_at, note, source, order_id, execution_id,
                      settlement_date, decision_price, arrival_price,
                      benchmark_price, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        activity.order_id,
                        activity.execution_id,
                        activity.settlement_date.isoformat()
                        if activity.settlement_date
                        else None,
                        activity.decision_price,
                        activity.arrival_price,
                        activity.benchmark_price,
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
            self._prepare(connection)
            cursor = connection.execute(
                """
                DELETE FROM portfolio_activities
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, activity_id),
            )
            if cursor.rowcount == 0:
                raise PortfolioNotFoundError("portfolio activity was not found")

    def get_risk_policy(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> PortfolioRiskPolicy:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM portfolio_risk_policy
                WHERE user_id = ? AND workspace_id = ?
                """,
                (user_id, workspace_id),
            ).fetchone()
            if row is None:
                policy = PortfolioRiskPolicyInput()
                now = self._now()
                connection.execute(
                    """
                    INSERT INTO portfolio_risk_policy (
                      user_id, workspace_id, single_position_limit_pct,
                      top_three_limit_pct, min_effective_positions,
                      max_drawdown_limit_pct, var95_limit_pct,
                      max_unpriced_positions, allow_negative_cash, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        workspace_id,
                        policy.single_position_limit_pct,
                        policy.top_three_limit_pct,
                        policy.min_effective_positions,
                        policy.max_drawdown_limit_pct,
                        policy.var95_limit_pct,
                        policy.max_unpriced_positions,
                        int(policy.allow_negative_cash),
                        now,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT * FROM portfolio_risk_policy
                    WHERE user_id = ? AND workspace_id = ?
                    """,
                    (user_id, workspace_id),
                ).fetchone()
        assert row is not None
        return self._risk_policy(row)

    def save_risk_policy(
        self,
        *,
        user_id: str,
        workspace_id: str,
        policy: PortfolioRiskPolicyInput,
    ) -> PortfolioRiskPolicy:
        now = self._now()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                INSERT INTO portfolio_risk_policy (
                  user_id, workspace_id, single_position_limit_pct,
                  top_three_limit_pct, min_effective_positions,
                  max_drawdown_limit_pct, var95_limit_pct,
                  max_unpriced_positions, allow_negative_cash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id) DO UPDATE SET
                  single_position_limit_pct = excluded.single_position_limit_pct,
                  top_three_limit_pct = excluded.top_three_limit_pct,
                  min_effective_positions = excluded.min_effective_positions,
                  max_drawdown_limit_pct = excluded.max_drawdown_limit_pct,
                  var95_limit_pct = excluded.var95_limit_pct,
                  max_unpriced_positions = excluded.max_unpriced_positions,
                  allow_negative_cash = excluded.allow_negative_cash,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    workspace_id,
                    policy.single_position_limit_pct,
                    policy.top_three_limit_pct,
                    policy.min_effective_positions,
                    policy.max_drawdown_limit_pct,
                    policy.var95_limit_pct,
                    policy.max_unpriced_positions,
                    int(policy.allow_negative_cash),
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM portfolio_risk_policy
                WHERE user_id = ? AND workspace_id = ?
                """,
                (user_id, workspace_id),
            ).fetchone()
        assert row is not None
        return self._risk_policy(row)

    def list_risk_actions(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> list[PortfolioRiskAction]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM portfolio_risk_actions
                WHERE user_id = ? AND workspace_id = ? AND source_snapshot_id IS NULL
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [self._risk_action(row) for row in rows]

    def create_risk_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action: PortfolioRiskActionCreate,
        source_snapshot_id: str | None = None,
    ) -> PortfolioRiskAction:
        identifier = str(uuid4())
        now = self._now()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute('BEGIN IMMEDIATE')
            if source_snapshot_id:
                existing = connection.execute('''SELECT * FROM portfolio_risk_actions
                    WHERE user_id=? AND workspace_id=? AND source_snapshot_id=? AND rule_id=?
                      AND status IN ('open','acknowledged')''',
                    (user_id, workspace_id, source_snapshot_id, action.rule_id)).fetchone()
                if existing:
                    return self._risk_action(existing)
            connection.execute(
                """
                INSERT INTO portfolio_risk_actions (
                  user_id, workspace_id, id, rule_id, severity, status,
                  title, detail, owner, note, created_at, updated_at, resolved_at, source_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    identifier,
                    action.rule_id,
                    action.severity,
                    action.title,
                    action.detail,
                    action.owner,
                    action.note,
                    now,
                    now,
                    source_snapshot_id,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM portfolio_risk_actions
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, identifier),
            ).fetchone()
        assert row is not None
        return self._risk_action(row)

    def list_snapshot_risk_actions(self, *, user_id: str, workspace_id: str, snapshot_id: str) -> list[PortfolioRiskAction]:
        saved = self.get_import_snapshot(user_id=user_id, workspace_id=workspace_id, snapshot_id=snapshot_id)
        product_id = saved['snapshot'].get('productId') or ''
        with self._connect() as connection:
            rows = connection.execute('''SELECT a.* FROM portfolio_risk_actions a
                JOIN portfolio_import_snapshots s ON s.id=a.source_snapshot_id
                  AND s.user_id=a.user_id AND s.workspace_id=a.workspace_id
                WHERE a.user_id=? AND a.workspace_id=?
                  AND (a.source_snapshot_id=? OR (?<>'' AND json_extract(s.snapshot,'$.productId')=?))
                ORDER BY a.updated_at DESC, a.id DESC''',
                (user_id, workspace_id, snapshot_id, product_id, product_id)).fetchall()
        return [self._risk_action(row) for row in rows]

    def update_risk_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action_id: str,
        update: PortfolioRiskActionUpdate,
    ) -> PortfolioRiskAction:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM portfolio_risk_actions
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, action_id),
            ).fetchone()
            if row is None:
                raise PortfolioNotFoundError("portfolio risk action was not found")
            current = self._risk_action(row)
            fields = update.model_fields_set
            status_value = update.status if "status" in fields else current.status
            status_value = status_value or current.status
            owner = update.owner if "owner" in fields else current.owner
            note = update.note if "note" in fields else current.note
            due_at = update.due_at if "due_at" in fields else current.due_at
            if current.status in {"resolved", "waived"}:
                raise PortfolioConflictError("已结案记录不可修改；如风险再次发生，请新建处置。")
            review_snapshot_id = update.review_snapshot_id if 'review_snapshot_id' in fields else current.review_snapshot_id
            if review_snapshot_id:
                if not current.source_snapshot_id or review_snapshot_id == current.source_snapshot_id:
                    raise PortfolioConflictError('复核须关联不同于来源的产品快照；原股票账本处置不支持此关联。')
                source = connection.execute('SELECT * FROM portfolio_import_snapshots WHERE user_id=? AND workspace_id=? AND id=?', (user_id, workspace_id, current.source_snapshot_id)).fetchone()
                review = connection.execute('SELECT * FROM portfolio_import_snapshots WHERE user_id=? AND workspace_id=? AND id=?', (user_id, workspace_id, review_snapshot_id)).fetchone()
                if source is None or review is None:
                    raise PortfolioNotFoundError('来源或复核快照不存在')
                old, new = json.loads(source['snapshot']), json.loads(review['snapshot'])
                if not old.get('productId') or new.get('productId') != old['productId']:
                    raise PortfolioConflictError('复核快照必须明确归属同一产品；未归属快照不能跨版本关联。')
                if new['asOf'] < old['asOf'] or review['saved_at'] <= source['saved_at']:
                    raise PortfolioConflictError('复核快照须为来源之后保存的版本，且持仓日不能早于来源。')
            if status_value != "open" and not owner:
                raise PortfolioConflictError("请填写处置负责人。")
            if status_value == "acknowledged" and not due_at:
                raise PortfolioConflictError("接手处置前请填写期限。")
            if status_value in {"resolved", "waived"} and not note:
                raise PortfolioConflictError("结案必须填写复核依据，豁免必须填写理由。")
            if status_value == 'resolved' and current.status != 'acknowledged':
                raise PortfolioConflictError('请先接手处理，再复核结案。')
            now = self._now()
            resolved_at = (
                now if status_value in {"resolved", "waived"} else None
            )
            connection.execute(
                """
                UPDATE portfolio_risk_actions
                SET status = ?, owner = ?, note = ?, due_at = ?, updated_at = ?, resolved_at = ?, review_snapshot_id = ?
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (
                    status_value,
                    owner,
                    note,
                    due_at.isoformat() if due_at else None,
                    now,
                    resolved_at,
                    review_snapshot_id,
                    user_id,
                    workspace_id,
                    action_id,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM portfolio_risk_actions
                WHERE user_id = ? AND workspace_id = ? AND id = ?
                """,
                (user_id, workspace_id, action_id),
            ).fetchone()
        assert row is not None
        return self._risk_action(row)

    def save_risk_report(self, dashboard: PortfolioDashboard, performance: PortfolioPerformanceResult | None = None, analysis_input: PortfolioPerformanceRequest | None = None) -> PortfolioRiskReport:
        report = PortfolioRiskReport(id=str(uuid4()), saved_at=datetime.now(UTC), dashboard=dashboard, performance=performance, analysis_input=analysis_input or PortfolioPerformanceRequest())
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                'INSERT INTO portfolio_risk_reports VALUES (?, ?, ?, ?, ?)',
                (dashboard.user_id, dashboard.workspace_id, report.id, report.saved_at.isoformat(), report.model_dump_json(by_alias=True)),
            )
        return report

    def list_risk_reports(self, *, user_id: str, workspace_id: str) -> list[PortfolioRiskReport]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                'SELECT payload FROM portfolio_risk_reports WHERE user_id = ? AND workspace_id = ? ORDER BY saved_at DESC LIMIT 50',
                (user_id, workspace_id),
            ).fetchall()
        return [PortfolioRiskReport.model_validate_json(row['payload']) for row in rows]

    def get_risk_report(self, *, user_id: str, workspace_id: str, report_id: str) -> PortfolioRiskReport:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                'SELECT payload FROM portfolio_risk_reports WHERE user_id = ? AND workspace_id = ? AND id = ?',
                (user_id, workspace_id, report_id),
            ).fetchone()
        if row is None:
            raise PortfolioNotFoundError('风险评估不存在或不属于当前工作区。')
        return PortfolioRiskReport.model_validate_json(row['payload'])

    def import_legacy_document(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document: dict,
        migration_id: str = "vibe-research-portfolio-json-v1",
    ) -> LegacyImportResult:
        with self._connect() as connection:
            self._prepare(connection)
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
            self._prepare(connection)
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
