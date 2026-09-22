import sqlite3


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """CREATE TABLE IF NOT EXISTS cursos (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
            cupos_totales INTEGER NOT NULL CHECK(cupos_totales >= 0),
            cupos_disponibles INTEGER NOT NULL CHECK(cupos_disponibles >= 0)
        )"""
    )
    return db


def seed(db: sqlite3.Connection) -> None:
    if db.execute("SELECT COUNT(*) FROM cursos").fetchone()[0]:
        return
    db.executemany(
        "INSERT INTO cursos VALUES (?, ?, ?, ?)",
        [("ARQ-101", "Arquitectura de Sistemas", 2, 2),
         ("API-201", "Integracion de APIs", 1, 1),
         ("DAT-110", "Fundamentos de Datos", 3, 3)],
    )
    db.commit()
