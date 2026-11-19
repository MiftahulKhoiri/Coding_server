"""Pelaksana file .sql untuk SQLite. Dipanggil sebagai proses terpisah oleh SqlEngine.

Pemakaian: python sql_runner.py [--check] FILE.sql DATABASE.db
"""
import sqlite3
import sys


def split_statements(sql: str) :
    """Pisahkan SQL menjadi pernyataan utuh (aman untuk ';' di dalam string/trigger)."""
    out, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            if buf.strip().strip(";").strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def print_table(cols, rows, limit=500):
    data = [[("NULL" if v is None else str(v)) for v in r] for r in rows[:limit]]
    widths = [max([len(c)] + [len(r[i]) for r in data]) for i, c in enumerate(cols)]
    widths = [min(w, 60) for w in widths]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(line)
    print("| " + " | ".join(c[:w].ljust(w) for c, w in zip(cols, widths)) + " |")
    print(line)
    for r in data:
        print("| " + " | ".join(v[:w].ljust(w) for v, w in zip(r, widths)) + " |")
    print(line)
    extra = f" (ditampilkan {limit})" if len(rows) > limit else ""
    print(f"{len(rows)} baris{extra}")


def main() -> int:
    args = sys.argv[1:]
    check = False
    if args and args[0] == "--check":
        check = True
        args = args[1:]
    if len(args) != 2:
        print("Pemakaian: sql_runner.py [--check] FILE.sql DATABASE.db", file=sys.stderr)
        return 2
    src, db = args
    sql = open(src, encoding="utf-8").read()
    stmts = split_statements(sql)
    if check:
        conn = sqlite3.connect(":memory:")
        bad = 0
        for i, s in enumerate(stmts, 1):
            if not sqlite3.complete_statement(s if s.endswith(";") else s + ";"):
                print(f"Pernyataan #{i} tidak lengkap", file=sys.stderr)
                bad += 1
        print(f"{len(stmts)} pernyataan diperiksa, {bad} bermasalah")
        conn.close()
        return 1 if bad else 0
    conn = sqlite3.connect(db)
    try:
        for i, s in enumerate(stmts, 1):
            cur = conn.execute(s)
            if cur.description:
                cols = [d[0] for d in cur.description]
                print_table(cols, cur.fetchall())
            else:
                print(f"OK: {s.split()[0].upper()} (baris terpengaruh: {cur.rowcount if cur.rowcount >= 0 else 0})")
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error SQL pada pernyataan #{i}: {e}", file=sys.stderr)
        conn.rollback()
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
