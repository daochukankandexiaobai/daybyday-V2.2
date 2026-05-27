from __future__ import annotations

from datetime import datetime

from app.config.field_compat import default_template_fields
from app.utils.hash_utils import generate_salt, hash_password
from app.utils.log_utils import get_logger


DEFAULT_TEMPLATE_NAME = "V1.0日报模板"
DEFAULT_TEMPLATE_VERSION = "2026.04.01"
SCHEMA_VERSION = "1.2"
BUSINESS_RULES_VERSION = "1.1"

LOGGER = get_logger("migrations")

DEFAULT_TEMPLATE_FIELDS = [
    (item["field_key"], item["field_label"], item["field_type"], item["is_required"], item["display_order"])
    for item in default_template_fields(include_future=False)
]


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _table_column_info(conn, table_name: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _ensure_column(conn, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def _has_column(conn, table_name: str, column_name: str) -> bool:
    return column_name in _table_columns(conn, table_name)


def _migrate_legacy_daily_records(conn) -> None:
    """将旧版本字段尽量映射到 V1.0 字段，避免升级后索引或查询失效。"""

    if not _has_column(conn, "daily_records", "id"):
        return

    # 旧字段 date -> 新字段 record_date
    if _has_column(conn, "daily_records", "date"):
        conn.execute(
            """
            UPDATE daily_records
            SET record_date = date
            WHERE (record_date IS NULL OR record_date = '')
              AND date IS NOT NULL
              AND date != ''
            """
        )

    # 旧字段 team -> team_name_snapshot
    if _has_column(conn, "daily_records", "team"):
        conn.execute(
            """
            UPDATE daily_records
            SET team_name_snapshot = team
            WHERE (team_name_snapshot IS NULL OR team_name_snapshot = '')
              AND team IS NOT NULL
              AND team != ''
            """
        )

    # 旧字段 manager_name 尽量拆分到快照字段（旧数据无法明确区分角色）
    if _has_column(conn, "daily_records", "manager_name"):
        conn.execute(
            """
            UPDATE daily_records
            SET account_manager_name_snapshot = manager_name
            WHERE (account_manager_name_snapshot IS NULL OR account_manager_name_snapshot = '')
              AND manager_name IS NOT NULL
              AND manager_name != ''
            """
        )
        conn.execute(
            """
            UPDATE daily_records
            SET team_manager_name_snapshot = manager_name
            WHERE (team_manager_name_snapshot IS NULL OR team_manager_name_snapshot = '')
              AND manager_name IS NOT NULL
              AND manager_name != ''
            """
        )

    # 确保关键键值不为空，避免唯一索引创建失败。
    conn.execute(
        """
        UPDATE daily_records
        SET record_date = COALESCE(NULLIF(record_date, ''), '1970-01-01')
        """
    )
    conn.execute(
        """
        UPDATE daily_records
        SET team_id = COALESCE(team_id, 0)
        """
    )
    conn.execute(
        """
        UPDATE daily_records
        SET account_manager_id = -id
        WHERE account_manager_id IS NULL OR account_manager_id = 0
        """
    )
    conn.execute(
        """
        UPDATE daily_records
        SET record_id = 'migrated-' || id
        WHERE record_id IS NULL OR record_id = ''
        """
    )
    conn.execute(
        """
        UPDATE daily_records
        SET business_key = COALESCE(
            NULLIF(business_key, ''),
            COALESCE(record_date, '') || '|' || COALESCE(region, '') || '|' || COALESCE(team_name_snapshot, '') || '|' || COALESCE(account_manager_name_snapshot, '')
        )
        """
    )


def _normalize_daily_record_cycle_codes(conn) -> None:
    """按 record_date 统一结算周期编码为“结束月命名”。

    例如：
    - 2026-03-29 ~ 2026-04-28 => 2026-04期
    """
    if not _has_column(conn, "daily_records", "settlement_cycle_code"):
        return
    if not _has_column(conn, "daily_records", "record_date"):
        return

    conn.execute(
        """
        UPDATE daily_records
        SET settlement_cycle_code = COALESCE(
            CASE
                WHEN record_date IS NULL OR record_date = '' THEN settlement_cycle_code
                WHEN CAST(strftime('%d', record_date) AS INTEGER) >= 29
                    THEN strftime('%Y-%m', date(record_date, 'start of month', '+1 month')) || '期'
                ELSE strftime('%Y-%m', date(record_date)) || '期'
            END,
            settlement_cycle_code
        )
        """
    )


def _deduplicate_for_unique_daily_key(conn) -> None:
    """按 V1 唯一键去重，保留同键的最新一条（id 最大）。"""

    source_columns = _table_column_info(conn, "daily_records")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_records_migration_backup AS
        SELECT *
        FROM daily_records
        WHERE 1 = 0
        """
    )

    backup_columns = _table_columns(conn, "daily_records_migration_backup")
    for column in source_columns:
        column_name = str(column["name"])
        if column_name in backup_columns:
            continue
        column_type = str(column.get("type") or "").strip() or "TEXT"
        conn.execute(
            "ALTER TABLE daily_records_migration_backup "
            f"ADD COLUMN {_quote_identifier(column_name)} {column_type}"
        )
        backup_columns.add(column_name)

    insert_columns = [str(column["name"]) for column in source_columns if str(column["name"]) in backup_columns]
    column_sql = ", ".join(_quote_identifier(column) for column in insert_columns)
    conn.execute(
        f"""
        INSERT INTO daily_records_migration_backup ({column_sql})
        SELECT {column_sql}
        FROM daily_records
        WHERE id IN (
            SELECT d.id
            FROM daily_records d
            JOIN (
                SELECT record_date, team_id, account_manager_id, MAX(id) AS keep_id
                FROM daily_records
                GROUP BY record_date, team_id, account_manager_id
            ) k
              ON d.record_date = k.record_date
             AND d.team_id = k.team_id
             AND d.account_manager_id = k.account_manager_id
            WHERE d.id != k.keep_id
        )
        """
    )

    backup_count = conn.execute(
        "SELECT COUNT(1) AS c FROM daily_records_migration_backup"
    ).fetchone()["c"]
    if int(backup_count) > 0:
        LOGGER.warning("迁移检测到重复记录，已备份到 daily_records_migration_backup，数量=%s", backup_count)

    conn.execute(
        """
        DELETE FROM daily_records
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM daily_records
            GROUP BY record_date, team_id, account_manager_id
        )
        """
    )


def run_migrations(db_manager) -> None:
    LOGGER.info("开始执行数据库迁移")
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT NOT NULL,
                team_name TEXT NOT NULL,
                team_manager_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(region, team_name, team_manager_name)
            );
            """
        )
        _ensure_column(conn, "teams", "is_active", "INTEGER DEFAULT 1")
        conn.execute("UPDATE teams SET is_active = 1 WHERE is_active IS NULL")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS account_managers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                account_manager_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(team_id, account_manager_name),
                FOREIGN KEY(team_id) REFERENCES teams(id)
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                account_manager_id INTEGER NOT NULL,
                settlement_cycle_code TEXT NOT NULL,
                target_amount REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(team_id, account_manager_id, settlement_cycle_code),
                FOREIGN KEY(team_id) REFERENCES teams(id),
                FOREIGN KEY(account_manager_id) REFERENCES account_managers(id)
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE NOT NULL,
                business_key TEXT DEFAULT '',
                record_date TEXT NOT NULL,
                region TEXT NOT NULL,
                team_id INTEGER NOT NULL DEFAULT 0,
                team_name_snapshot TEXT NOT NULL DEFAULT '',
                team_manager_name_snapshot TEXT NOT NULL DEFAULT '',
                account_manager_id INTEGER NOT NULL DEFAULT 0,
                account_manager_name_snapshot TEXT NOT NULL DEFAULT '',
                settlement_cycle_code TEXT NOT NULL DEFAULT '',
                repayment_amount_daily REAL DEFAULT 0,
                loan_amount_daily REAL DEFAULT 0,
                intention_daily INTEGER DEFAULT 0,
                wechat_count_daily INTEGER DEFAULT 0,
                visit_count_daily INTEGER DEFAULT 0,
                invalid_visit_count_daily INTEGER DEFAULT 0,
                signing_count_daily INTEGER DEFAULT 0,
                quality_visit_count_daily INTEGER DEFAULT 0,
                approval_customer_count_daily INTEGER DEFAULT 0,
                repayment_customer_count_daily INTEGER DEFAULT 0,
                debt_case_submit_count_daily INTEGER DEFAULT 0,
                debt_case_repayment_count_daily INTEGER DEFAULT 0,
                debt_case_repayment_amount_daily REAL DEFAULT 0,
                large_order_repayment_count_daily INTEGER DEFAULT 0,
                large_order_repayment_amount_daily REAL DEFAULT 0,
                four_star_customer_count_daily INTEGER DEFAULT 0,
                five_star_customer_count_daily INTEGER DEFAULT 0,
                remark TEXT,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                template_version TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                source_type TEXT DEFAULT 'local',
                source_file TEXT
            );
            """
        )

        for column_name, ddl in [
            ("record_date", "TEXT"),
            ("business_key", "TEXT DEFAULT ''"),
            ("team_id", "INTEGER DEFAULT 0"),
            ("team_name_snapshot", "TEXT DEFAULT ''"),
            ("team_manager_name_snapshot", "TEXT DEFAULT ''"),
            ("account_manager_id", "INTEGER DEFAULT 0"),
            ("account_manager_name_snapshot", "TEXT DEFAULT ''"),
            ("settlement_cycle_code", "TEXT DEFAULT ''"),
            ("repayment_amount_daily", "REAL DEFAULT 0"),
            ("loan_amount_daily", "REAL DEFAULT 0"),
            ("intention_daily", "INTEGER DEFAULT 0"),
            ("wechat_count_daily", "INTEGER DEFAULT 0"),
            ("visit_count_daily", "INTEGER DEFAULT 0"),
            ("invalid_visit_count_daily", "INTEGER DEFAULT 0"),
            ("signing_count_daily", "INTEGER DEFAULT 0"),
            ("quality_visit_count_daily", "INTEGER DEFAULT 0"),
            ("approval_customer_count_daily", "INTEGER DEFAULT 0"),
            ("repayment_customer_count_daily", "INTEGER DEFAULT 0"),
            ("debt_case_submit_count_daily", "INTEGER DEFAULT 0"),
            ("debt_case_repayment_count_daily", "INTEGER DEFAULT 0"),
            ("debt_case_repayment_amount_daily", "REAL DEFAULT 0"),
            ("large_order_repayment_count_daily", "INTEGER DEFAULT 0"),
            ("large_order_repayment_amount_daily", "REAL DEFAULT 0"),
            ("four_star_customer_count_daily", "INTEGER DEFAULT 0"),
            ("five_star_customer_count_daily", "INTEGER DEFAULT 0"),
        ]:
            _ensure_column(conn, "daily_records", column_name, ddl)

        cursor.execute("DROP INDEX IF EXISTS idx_daily_records_unique_v1")
        _migrate_legacy_daily_records(conn)
        _normalize_daily_record_cycle_codes(conn)
        _deduplicate_for_unique_daily_key(conn)
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_records_unique_v1 "
            "ON daily_records(team_id, account_manager_id, record_date);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_records_record_date ON daily_records(record_date);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_records_settlement_cycle_code ON daily_records(settlement_cycle_code);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_records_cycle_date ON daily_records(settlement_cycle_code, record_date);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_account_managers_team ON account_managers(team_id, is_active);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_cycle_targets_cycle ON cycle_targets(team_id, settlement_cycle_code);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(is_active, updated_at DESC, id DESC);"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS import_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_time TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT,
                export_id TEXT,
                team_name TEXT,
                settlement_cycle_code TEXT,
                template_version TEXT,
                result TEXT NOT NULL,
                message TEXT,
                affected_record_count INTEGER DEFAULT 0,
                log_type TEXT DEFAULT 'import',
                operator TEXT,
                recognized_summary TEXT,
                final_team TEXT,
                range_start TEXT,
                range_end TEXT,
                replaced_member_count INTEGER DEFAULT 0,
                replaced_record_count INTEGER DEFAULT 0
            );
            """
        )
        _ensure_column(conn, "import_logs", "team_name", "TEXT")
        _ensure_column(conn, "import_logs", "settlement_cycle_code", "TEXT")
        _ensure_column(conn, "import_logs", "log_type", "TEXT DEFAULT 'import'")
        _ensure_column(conn, "import_logs", "operator", "TEXT")
        _ensure_column(conn, "import_logs", "recognized_summary", "TEXT")
        _ensure_column(conn, "import_logs", "final_team", "TEXT")
        _ensure_column(conn, "import_logs", "range_start", "TEXT")
        _ensure_column(conn, "import_logs", "range_end", "TEXT")
        _ensure_column(conn, "import_logs", "replaced_member_count", "INTEGER DEFAULT 0")
        _ensure_column(conn, "import_logs", "replaced_record_count", "INTEGER DEFAULT 0")
        conn.execute("UPDATE import_logs SET log_type = 'import' WHERE log_type IS NULL OR log_type = ''")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_import_logs_import_time ON import_logs(import_time);"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                template_version TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS template_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                field_key TEXT NOT NULL,
                field_label TEXT NOT NULL,
                field_type TEXT NOT NULL,
                is_required INTEGER DEFAULT 0,
                display_order INTEGER DEFAULT 0,
                FOREIGN KEY(template_id) REFERENCES templates(id)
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                operator TEXT NOT NULL,
                action_time TEXT NOT NULL,
                before_snapshot TEXT,
                after_snapshot TEXT,
                note TEXT
            );
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_action_logs_time ON admin_action_logs(action_time DESC, id DESC);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_action_logs_target ON admin_action_logs(target_type, target_id);"
        )

        _bootstrap_defaults(conn)
        conn.commit()
    LOGGER.info("数据库迁移完成，schema_version=%s business_rules_version=%s", SCHEMA_VERSION, BUSINESS_RULES_VERSION)


def _bootstrap_defaults(conn) -> None:
    now = _now_str()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(1) AS c FROM admin_users")
    if cursor.fetchone()["c"] == 0:
        salt = generate_salt()
        password_hash = hash_password("admin123", salt)
        cursor.execute(
            """
            INSERT INTO admin_users (username, password_hash, salt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("admin", password_hash, salt, now, now),
        )

    defaults = {
        "company_name": "示例公司",
        "default_export_dir": "",
        "app_version": "1.1-win7",
        "strict_template_mode": "1",
        "view_scale_mode": "auto",
        "view_scale_factor": "1.00",
        "schema_version": SCHEMA_VERSION,
        "business_rules_version": BUSINESS_RULES_VERSION,
    }
    for key, value in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))

    cursor.execute("SELECT id, template_version FROM templates WHERE template_version = ?", (DEFAULT_TEMPLATE_VERSION,))
    tpl = cursor.fetchone()
    if tpl is None:
        cursor.execute(
            """
            INSERT INTO templates (template_name, template_version, is_active, created_at)
            VALUES (?, ?, 0, ?)
            """,
            (DEFAULT_TEMPLATE_NAME, DEFAULT_TEMPLATE_VERSION, now),
        )
        template_id = int(cursor.lastrowid)
    else:
        template_id = int(tpl["id"])

    existing_field_keys = {
        str(row["field_key"])
        for row in cursor.execute(
            "SELECT field_key FROM template_fields WHERE template_id = ?",
            (template_id,),
        ).fetchall()
    }
    for field_key, field_label, field_type, is_required, display_order in DEFAULT_TEMPLATE_FIELDS:
        if field_key in existing_field_keys:
            cursor.execute(
                """
                UPDATE template_fields
                SET field_label = ?, field_type = ?, is_required = ?, display_order = ?
                WHERE template_id = ? AND field_key = ?
                """,
                (field_label, field_type, is_required, display_order, template_id, field_key),
            )
            continue
        cursor.execute(
            """
            INSERT INTO template_fields
            (template_id, field_key, field_label, field_type, is_required, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (template_id, field_key, field_label, field_type, is_required, display_order),
        )

    active = cursor.execute("SELECT id, template_version FROM templates WHERE is_active = 1 LIMIT 1").fetchone()
    if active is None:
        cursor.execute("UPDATE templates SET is_active = 0")
        cursor.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (template_id,))
        active_version = DEFAULT_TEMPLATE_VERSION
    else:
        active_version = str(active["template_version"])

    cursor.execute(
        "INSERT INTO app_settings (key, value) VALUES ('template_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (active_version,),
    )
    cursor.execute(
        "INSERT INTO app_settings (key, value) VALUES ('current_template_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (active_version,),
    )
    cursor.execute(
        "INSERT INTO app_settings (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    cursor.execute(
        "INSERT INTO app_settings (key, value) VALUES ('business_rules_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (BUSINESS_RULES_VERSION,),
    )

    team_row = cursor.execute(
        "SELECT id FROM teams WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    team_id = int(team_row["id"]) if team_row is not None else 0

    cursor.execute(
        "INSERT INTO app_settings (key, value) VALUES ('current_team_id', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(team_id),),
    )
