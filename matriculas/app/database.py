import sqlite3


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(
        """CREATE TABLE IF NOT EXISTS estudiantes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, email TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS matriculas (
            id TEXT PRIMARY KEY, estudiante_id TEXT NOT NULL, curso_id TEXT NOT NULL,
            estado TEXT NOT NULL CHECK(estado IN ('activa', 'revertida')),
            creada_en TEXT NOT NULL, FOREIGN KEY(estudiante_id) REFERENCES estudiantes(id)
        );
        CREATE TABLE IF NOT EXISTS idempotencia (
            clave TEXT PRIMARY KEY, respuesta TEXT NOT NULL, expira_en INTEGER NOT NULL
        );"""
    )
    db.commit()
    return db
