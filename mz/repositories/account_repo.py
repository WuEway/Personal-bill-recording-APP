from __future__ import annotations

import sqlite3

from mz.models.account import Account, AccountType


class AccountRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(
        self,
        type: AccountType,
        name: str,
        institution: str | None = None,
        last_4: str | None = None,
        is_credit: bool = False,
    ) -> Account:
        row = self.conn.execute(
            "SELECT * FROM accounts WHERE type=? AND COALESCE(last_4,'')=? AND COALESCE(institution,'')=?",
            (type, last_4 or "", institution or ""),
        ).fetchone()
        if row:
            return self._from_row(row)

        cur = self.conn.execute(
            "INSERT INTO accounts(type, name, institution, last_4, is_credit) VALUES(?,?,?,?,?)",
            (type, name, institution, last_4, int(is_credit)),
        )
        self.conn.commit()
        return Account(
            id=cur.lastrowid,
            type=type,
            name=name,
            institution=institution,
            last_4=last_4,
            is_credit=is_credit,
        )

    def get_by_id(self, account_id: int) -> Account | None:
        row = self.conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> list[Account]:
        rows = self.conn.execute("SELECT * FROM accounts ORDER BY institution, name").fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            institution=row["institution"],
            last_4=row["last_4"],
            is_credit=bool(row["is_credit"]),
            is_active=bool(row["is_active"]),
        )
