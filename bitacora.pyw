from __future__ import annotations

import sqlite3
import sys
import tempfile
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "datos" / "bitacora.db"

COLORS = {
    "navy": "#152238",
    "blue": "#2855A6",
    "sky": "#DCE8F8",
    "ice": "#F4F7FB",
    "green": "#2E7D5B",
    "green_soft": "#DDF1E7",
    "amber": "#C78318",
    "amber_soft": "#FFF0D5",
    "red": "#B64949",
    "red_soft": "#F8DDDD",
    "ink": "#243247",
    "muted": "#65758B",
    "white": "#FFFFFF",
}


class Database:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                initial_balance REAL NOT NULL DEFAULT 0,
                monthly_goal REAL NOT NULL DEFAULT 0,
                minimum_payment REAL NOT NULL DEFAULT 0,
                no_interest_payment REAL NOT NULL DEFAULT 0,
                target_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_entries (
                entry_date TEXT PRIMARY KEY,
                cisco_modules INTEGER NOT NULL DEFAULT 0,
                uveg_progress REAL NOT NULL DEFAULT 0,
                tuch_progress REAL NOT NULL DEFAULT 0,
                argos_minutes INTEGER NOT NULL DEFAULT 0,
                centinela_minutes INTEGER NOT NULL DEFAULT 0,
                exercise INTEGER NOT NULL DEFAULT 0,
                english_minutes INTEGER NOT NULL DEFAULT 0,
                debt_id INTEGER,
                debt_payment REAL NOT NULL DEFAULT 0,
                avoided_spending REAL NOT NULL DEFAULT 0,
                nofap TEXT NOT NULL DEFAULT '',
                sleep_hours REAL NOT NULL DEFAULT 0,
                energy INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (debt_id) REFERENCES debts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS debt_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id INTEGER NOT NULL,
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                legacy_entry_date TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (debt_id) REFERENCES debts(id) ON DELETE CASCADE
            );
            """
        )
        debt_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(debts)")}
        for name in ("minimum_payment", "no_interest_payment"):
            if name not in debt_columns:
                self.conn.execute(f"ALTER TABLE debts ADD COLUMN {name} REAL NOT NULL DEFAULT 0")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO debt_payments
                (debt_id, payment_date, amount, note, legacy_entry_date)
            SELECT debt_id, entry_date, debt_payment, 'Migrado desde registro diario', entry_date
            FROM daily_entries
            WHERE debt_id IS NOT NULL AND debt_payment > 0
            """
        )
        self.conn.execute(
            "UPDATE daily_entries SET debt_payment=0 WHERE debt_id IS NOT NULL AND debt_payment > 0"
        )
        self.conn.commit()

    def save_entry(self, data: dict):
        columns = [
            "entry_date", "cisco_modules", "uveg_progress", "tuch_progress",
            "argos_minutes", "centinela_minutes", "exercise", "english_minutes",
            "debt_id", "debt_payment", "avoided_spending", "nofap",
            "sleep_hours", "energy", "note",
        ]
        values = [data[column] for column in columns]
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
        self.conn.execute(
            f"""
            INSERT INTO daily_entries ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(entry_date) DO UPDATE SET
                {updates}, updated_at=CURRENT_TIMESTAMP
            """,
            values,
        )
        self.conn.commit()

    def get_entry(self, entry_date: str):
        return self.conn.execute(
            "SELECT * FROM daily_entries WHERE entry_date = ?", (entry_date,)
        ).fetchone()

    def list_entries(self, limit: int = 365):
        return self.conn.execute(
            """
            SELECT e.*, d.name AS debt_name,
                   COALESCE((SELECT SUM(p.amount) FROM debt_payments p
                             WHERE p.payment_date=e.entry_date), 0) AS payments_on_date
            FROM daily_entries e
            LEFT JOIN debts d ON d.id = e.debt_id
            ORDER BY e.entry_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def delete_entry(self, entry_date: str):
        self.conn.execute("DELETE FROM daily_entries WHERE entry_date = ?", (entry_date,))
        self.conn.commit()

    def save_debt(self, debt_id, name, initial_balance, monthly_goal, minimum_payment, no_interest_payment, target_date):
        if debt_id:
            self.conn.execute(
                """
                UPDATE debts
                SET name=?, initial_balance=?, monthly_goal=?, minimum_payment=?,
                    no_interest_payment=?, target_date=?
                WHERE id=?
                """,
                (name, initial_balance, monthly_goal, minimum_payment, no_interest_payment, target_date or None, debt_id),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO debts
                    (name, initial_balance, monthly_goal, minimum_payment, no_interest_payment, target_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, initial_balance, monthly_goal, minimum_payment, no_interest_payment, target_date or None),
            )
        self.conn.commit()

    def delete_debt(self, debt_id: int):
        self.conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
        self.conn.commit()

    def list_debts(self):
        month_start = date.today().replace(day=1).isoformat()
        month_end = date.today().replace(day=calendar.monthrange(date.today().year, date.today().month)[1]).isoformat()
        return self.conn.execute(
            """
            SELECT d.*,
                   COALESCE(SUM(p.amount), 0) AS paid,
                   COALESCE(SUM(CASE WHEN p.payment_date BETWEEN ? AND ? THEN p.amount ELSE 0 END), 0) AS paid_month,
                   MAX(0, d.initial_balance - COALESCE(SUM(p.amount), 0)) AS pending
            FROM debts d
            LEFT JOIN debt_payments p ON p.debt_id = d.id
            GROUP BY d.id
            ORDER BY pending DESC, d.name
            """,
            (month_start, month_end),
        ).fetchall()

    def add_payment(self, debt_id: int, payment_date: str, amount: float, note: str = ""):
        self.conn.execute(
            "INSERT INTO debt_payments (debt_id, payment_date, amount, note) VALUES (?, ?, ?, ?)",
            (debt_id, payment_date, amount, note),
        )
        self.conn.commit()

    def list_payments(self, limit: int = 500):
        return self.conn.execute(
            """
            SELECT p.*, d.name AS debt_name
            FROM debt_payments p
            JOIN debts d ON d.id=p.debt_id
            ORDER BY p.payment_date DESC, p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def delete_payment(self, payment_id: int):
        self.conn.execute("DELETE FROM debt_payments WHERE id=?", (payment_id,))
        self.conn.commit()

    def payments_by_month(self, months: int = 12):
        return self.conn.execute(
            """
            SELECT substr(payment_date, 1, 7) AS month, SUM(amount) AS amount
            FROM debt_payments
            GROUP BY substr(payment_date, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (months,),
        ).fetchall()

    def entries_for_period(self, days: int):
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        return self.conn.execute(
            "SELECT * FROM daily_entries WHERE entry_date>=? ORDER BY entry_date",
            (start,),
        ).fetchall()

    def dashboard(self):
        today = date.today()
        start = (today - timedelta(days=6)).isoformat()
        end = today.isoformat()
        summary = self.conn.execute(
            """
            SELECT COUNT(*) AS days,
                   COALESCE(AVG(NULLIF(energy, 0)), 0) AS energy,
                   COALESCE(AVG(NULLIF(sleep_hours, 0)), 0) AS sleep,
                   COALESCE(SUM(cisco_modules), 0) AS cisco,
                   COALESCE(SUM(english_minutes), 0) AS english,
                   COALESCE(SUM(exercise), 0) AS exercise,
                   COALESCE(SUM(avoided_spending), 0) AS avoided
            FROM daily_entries
            WHERE entry_date BETWEEN ? AND ?
            """,
            (start, end),
        ).fetchone()
        debt = self.conn.execute(
            """
            SELECT COALESCE(SUM(initial_balance), 0) AS initial_balance,
                   COALESCE((SELECT SUM(amount) FROM debt_payments), 0) AS paid
            FROM debts
            """
        ).fetchone()
        recent = self.conn.execute(
            """
            SELECT * FROM daily_entries
            WHERE entry_date BETWEEN ? AND ?
            ORDER BY entry_date
            """,
            (start, end),
        ).fetchall()
        paid_week = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM debt_payments WHERE payment_date BETWEEN ? AND ?",
            (start, end),
        ).fetchone()[0]
        return summary, max(0, debt["initial_balance"] - debt["paid"]), recent, paid_week

    def close(self):
        self.conn.close()


def parse_number(value: str, label: str, kind=float, minimum=0, maximum=None):
    value = value.strip()
    if not value:
        return kind(0)
    try:
        result = kind(value)
    except ValueError as exc:
        raise ValueError(f"{label} debe ser un número válido.") from exc
    if result < minimum or (maximum is not None and result > maximum):
        limit = f" entre {minimum} y {maximum}" if maximum is not None else f" mayor o igual a {minimum}"
        raise ValueError(f"{label} debe estar{limit}.")
    return result


def validate_date(value: str, allow_blank=False):
    value = value.strip()
    if allow_blank and not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("La fecha debe usar el formato AAAA-MM-DD.") from exc


def compliance(entry) -> float:
    checks = [
        bool(entry["exercise"]),
        entry["english_minutes"] > 0,
        entry["nofap"] == "Cumplido",
        entry["sleep_hours"] >= 7,
        sum(entry[key] for key in ("cisco_modules", "uveg_progress", "tuch_progress", "argos_minutes", "centinela_minutes")) > 0,
    ]
    return sum(checks) / len(checks) * 100


class BitacoraApp(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.title("Proyecto Bitácora 1.1")
        self.geometry("1320x820")
        self.minsize(1050, 680)
        self.configure(bg=COLORS["ice"])
        self.debt_lookup = {}
        self.selected_debt_id = None
        self._style()
        self._build()
        self.refresh_all()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), foreground=COLORS["ink"])
        style.configure("TFrame", background=COLORS["ice"])
        style.configure("Card.TFrame", background=COLORS["white"], relief="solid", borderwidth=1)
        style.configure("TLabel", background=COLORS["ice"])
        style.configure("Title.TLabel", background=COLORS["navy"], foreground=COLORS["white"], font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["navy"], foreground="#D8E4F3", font=("Segoe UI", 9, "italic"))
        style.configure("Section.TLabel", background=COLORS["sky"], foreground=COLORS["navy"], font=("Segoe UI", 11, "bold"), padding=7)
        style.configure("CardLabel.TLabel", background=COLORS["white"], foreground=COLORS["muted"], font=("Segoe UI", 9, "bold"))
        style.configure("CardValue.TLabel", background=COLORS["white"], foreground=COLORS["navy"], font=("Segoe UI", 20, "bold"))
        style.configure("Accent.TButton", background=COLORS["blue"], foreground=COLORS["white"], font=("Segoe UI", 10, "bold"), padding=7)
        style.map("Accent.TButton", background=[("active", "#1F468D")])
        style.configure("Danger.TButton", background=COLORS["red"], foreground=COLORS["white"])
        style.configure("Treeview", rowheight=28, background=COLORS["white"], fieldbackground=COLORS["white"])
        style.configure("Treeview.Heading", background=COLORS["blue"], foreground=COLORS["white"], font=("Segoe UI", 9, "bold"))
        style.configure("TNotebook", background=COLORS["ice"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI", 10, "bold"))

    def _build(self):
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="PROYECTO BITÁCORA", style="Title.TLabel", padding=(22, 12, 10, 0)).pack(fill="x")
        ttk.Label(header, text="Sistema de progreso personal y académico", style="Subtitle.TLabel", padding=(24, 0, 10, 10)).pack(fill="x")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=12)
        self.panel_tab = ttk.Frame(self.tabs)
        self.entry_tab = ttk.Frame(self.tabs)
        self.history_tab = ttk.Frame(self.tabs)
        self.debts_tab = ttk.Frame(self.tabs)
        self.graphs_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.panel_tab, text="Panel")
        self.tabs.add(self.entry_tab, text="Registro diario")
        self.tabs.add(self.history_tab, text="Historial")
        self.tabs.add(self.debts_tab, text="Deudas y pagos")
        self.tabs.add(self.graphs_tab, text="Gráficas")
        self._build_panel()
        self._build_entry()
        self._build_history()
        self._build_debts()
        self._build_graphs()

    def _build_panel(self):
        self.cards_frame = ttk.Frame(self.panel_tab)
        self.cards_frame.pack(fill="x", pady=(4, 12))
        self.card_values = {}
        for key, label in [
            ("days", "DÍAS REGISTRADOS (7D)"),
            ("compliance", "CUMPLIMIENTO PROMEDIO"),
            ("energy", "ENERGÍA PROMEDIO"),
            ("debt", "SALDO DE DEUDAS"),
        ]:
            card = ttk.Frame(self.cards_frame, style="Card.TFrame", padding=14)
            card.pack(side="left", fill="x", expand=True, padx=5)
            ttk.Label(card, text=label, style="CardLabel.TLabel").pack()
            value = ttk.Label(card, text="0", style="CardValue.TLabel")
            value.pack(pady=(7, 2))
            self.card_values[key] = value

        lower = ttk.Frame(self.panel_tab)
        lower.pack(fill="both", expand=True)
        stats = ttk.Frame(lower, style="Card.TFrame", padding=12)
        stats.pack(side="left", fill="both", expand=True, padx=(5, 6))
        ttk.Label(stats, text="Últimos 7 días", style="Section.TLabel").pack(fill="x")
        self.week_tree = ttk.Treeview(stats, columns=("metric", "value"), show="headings", height=8)
        self.week_tree.heading("metric", text="Indicador")
        self.week_tree.heading("value", text="Resultado")
        self.week_tree.column("metric", width=210)
        self.week_tree.column("value", width=130, anchor="e")
        self.week_tree.pack(fill="x", pady=8)
        ttk.Label(stats, text="Tendencia diaria", style="Section.TLabel").pack(fill="x", pady=(8, 0))
        self.chart = tk.Canvas(stats, height=230, bg=COLORS["white"], highlightthickness=0)
        self.chart.pack(fill="both", expand=True, pady=5)

        recent_frame = ttk.Frame(lower, style="Card.TFrame", padding=12)
        recent_frame.pack(side="left", fill="both", expand=True, padx=(6, 5))
        ttk.Label(recent_frame, text="Registros recientes", style="Section.TLabel").pack(fill="x")
        self.recent_tree = ttk.Treeview(
            recent_frame, columns=("date", "energy", "sleep", "compliance", "note"), show="headings", height=16
        )
        for col, text, width in [
            ("date", "Fecha", 100), ("energy", "Energía", 70), ("sleep", "Sueño", 70),
            ("compliance", "Cumpl.", 75), ("note", "Nota", 250),
        ]:
            self.recent_tree.heading(col, text=text)
            self.recent_tree.column(col, width=width, anchor="w" if col == "note" else "center")
        self.recent_tree.pack(fill="both", expand=True, pady=8)
        self.recent_tree.bind("<Double-1>", self.open_recent)

    def _field(self, parent, label, variable, row, col, values=None, width=18):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky="ew", padx=7, pady=5)
        ttk.Label(frame, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        if values is None:
            widget = ttk.Entry(frame, textvariable=variable, width=width)
        else:
            widget = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=width)
        widget.pack(fill="x", pady=(3, 0))
        return widget

    def _build_entry(self):
        toolbar = ttk.Frame(self.entry_tab)
        toolbar.pack(fill="x", pady=(3, 8))
        self.entry_date = tk.StringVar(value=date.today().isoformat())
        ttk.Label(toolbar, text="Fecha (AAAA-MM-DD):", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(5, 5))
        ttk.Entry(toolbar, textvariable=self.entry_date, width=14).pack(side="left")
        ttk.Button(toolbar, text="Cargar fecha", command=self.load_entry).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Hoy", command=self.today_entry).pack(side="left")
        ttk.Button(toolbar, text="Guardar registro", style="Accent.TButton", command=self.save_entry).pack(side="right", padx=5)

        form = ttk.Frame(self.entry_tab, style="Card.TFrame", padding=14)
        form.pack(fill="both", expand=True, padx=5, pady=3)
        for col in range(4):
            form.columnconfigure(col, weight=1)

        self.entry_vars = {
            "cisco_modules": tk.StringVar(), "uveg_progress": tk.StringVar(),
            "tuch_progress": tk.StringVar(), "argos_minutes": tk.StringVar(),
            "centinela_minutes": tk.StringVar(), "exercise": tk.StringVar(value="No"),
            "english_minutes": tk.StringVar(), "debt_name": tk.StringVar(),
            "debt_payment": tk.StringVar(), "avoided_spending": tk.StringVar(),
            "nofap": tk.StringVar(), "sleep_hours": tk.StringVar(),
            "energy": tk.StringVar(), "note": tk.StringVar(),
        }
        ttk.Label(form, text="Avance académico y técnico", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 5))
        fields = [
            ("Cisco: submódulos", "cisco_modules"), ("UVEG: avance %", "uveg_progress"),
            ("TUCH: avance %", "tuch_progress"), ("Argos: minutos", "argos_minutes"),
            ("Centinela: minutos", "centinela_minutes"), ("Inglés: minutos", "english_minutes"),
        ]
        for i, (label, key) in enumerate(fields):
            self._field(form, label, self.entry_vars[key], 1 + i // 4, i % 4)

        ttk.Label(form, text="Hábitos y bienestar", style="Section.TLabel").grid(row=3, column=0, columnspan=4, sticky="ew", pady=(16, 5))
        self._field(form, "Ejercicio", self.entry_vars["exercise"], 4, 0, ["Sí", "No"])
        self._field(form, "NoFap", self.entry_vars["nofap"], 4, 1, ["Cumplido", "Reinicio", ""])
        self._field(form, "Sueño: horas", self.entry_vars["sleep_hours"], 4, 2)
        self._field(form, "Energía: 1-10", self.entry_vars["energy"], 4, 3)

        ttk.Label(form, text="Finanzas", style="Section.TLabel").grid(row=5, column=0, columnspan=4, sticky="ew", pady=(16, 5))
        self.debt_combo = self._field(form, "Deuda / cuenta", self.entry_vars["debt_name"], 6, 0, [""])
        self._field(form, "Pago nuevo (se agrega al historial)", self.entry_vars["debt_payment"], 6, 1)
        self._field(form, "Gasto evitado", self.entry_vars["avoided_spending"], 6, 2)

        ttk.Label(form, text="Nota breve", style="Section.TLabel").grid(row=7, column=0, columnspan=4, sticky="ew", pady=(16, 5))
        note = ttk.Entry(form, textvariable=self.entry_vars["note"])
        note.grid(row=8, column=0, columnspan=4, sticky="ew", padx=7, pady=5)
        ttk.Label(form, text="Registra datos reales. Un reinicio es información, no una sentencia.", foreground=COLORS["muted"]).grid(
            row=9, column=0, columnspan=4, sticky="w", padx=7, pady=14
        )

    def _build_history(self):
        toolbar = ttk.Frame(self.history_tab)
        toolbar.pack(fill="x", pady=(3, 8))
        ttk.Label(toolbar, text="Doble clic para abrir un registro.", foreground=COLORS["muted"]).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Actualizar", command=self.refresh_history).pack(side="right", padx=5)
        ttk.Button(toolbar, text="Eliminar seleccionado", style="Danger.TButton", command=self.delete_history).pack(side="right")
        frame = ttk.Frame(self.history_tab, style="Card.TFrame", padding=10)
        frame.pack(fill="both", expand=True, padx=5)
        columns = ("date", "cisco", "uveg", "tuch", "exercise", "english", "sleep", "energy", "compliance", "payment", "note")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings")
        headings = [
            ("date", "Fecha", 95), ("cisco", "Cisco", 55), ("uveg", "UVEG %", 65),
            ("tuch", "TUCH %", 65), ("exercise", "Ejercicio", 70), ("english", "Inglés", 60),
            ("sleep", "Sueño", 55), ("energy", "Energía", 60), ("compliance", "Cumpl.", 65),
            ("payment", "Pago", 80), ("note", "Nota", 240),
        ]
        for col, label, width in headings:
            self.history_tree.heading(col, text=label)
            self.history_tree.column(col, width=width, anchor="w" if col == "note" else "center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scroll.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.history_tree.bind("<Double-1>", self.open_history)

    def _build_debts(self):
        content = ttk.Frame(self.debts_tab)
        content.pack(fill="both", expand=True, padx=5, pady=3)
        editor = ttk.Frame(content, style="Card.TFrame", padding=14)
        editor.pack(side="left", fill="y", padx=(0, 7))
        ttk.Label(editor, text="Agregar o editar deuda", style="Section.TLabel").pack(fill="x", pady=(0, 10))
        self.debt_vars = {
            "name": tk.StringVar(), "initial": tk.StringVar(),
            "monthly": tk.StringVar(), "minimum": tk.StringVar(),
            "no_interest": tk.StringVar(), "target": tk.StringVar(),
        }
        for label, key in [
            ("Nombre de la deuda", "name"), ("Saldo inicial", "initial"),
            ("Meta mensual", "monthly"), ("Pago mínimo", "minimum"),
            ("Pago para no generar intereses", "no_interest"),
            ("Fecha objetivo (AAAA-MM-DD)", "target"),
        ]:
            ttk.Label(editor, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
            ttk.Entry(editor, textvariable=self.debt_vars[key], width=28).pack(fill="x", pady=(3, 0))
        ttk.Button(editor, text="Guardar deuda", style="Accent.TButton", command=self.save_debt).pack(fill="x", pady=(18, 5))
        ttk.Button(editor, text="Limpiar formulario", command=self.clear_debt_form).pack(fill="x", pady=5)
        ttk.Button(editor, text="Eliminar deuda", style="Danger.TButton", command=self.delete_debt).pack(fill="x", pady=5)

        frame = ttk.Frame(content, style="Card.TFrame", padding=10)
        frame.pack(side="left", fill="both", expand=True)
        ttk.Label(frame, text="Estado de deudas", style="Section.TLabel").pack(fill="x", pady=(0, 8))
        columns = ("name", "pending", "paid_month", "minimum", "no_interest", "monthly", "status")
        self.debt_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col, label, width in [
            ("name", "Deuda", 145), ("pending", "Pendiente", 100),
            ("paid_month", "Pagado este mes", 115), ("minimum", "Mínimo", 90),
            ("no_interest", "Sin intereses", 105), ("monthly", "Meta mensual", 100),
            ("status", "Estado mensual", 125),
        ]:
            self.debt_tree.heading(col, text=label)
            self.debt_tree.column(col, width=width, anchor="w" if col == "name" else "center")
        self.debt_tree.pack(fill="both", expand=True)
        self.debt_tree.bind("<<TreeviewSelect>>", self.select_debt)

        payments = ttk.Frame(frame)
        payments.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(payments, text="Movimientos de pago", style="Section.TLabel").pack(fill="x")
        pay_form = ttk.Frame(payments)
        pay_form.pack(fill="x", pady=7)
        self.payment_vars = {
            "date": tk.StringVar(value=date.today().isoformat()),
            "debt": tk.StringVar(), "amount": tk.StringVar(), "note": tk.StringVar(),
        }
        for label, key, width in [
            ("Fecha", "date", 12), ("Deuda", "debt", 18), ("Cantidad", "amount", 12), ("Nota", "note", 20),
        ]:
            ttk.Label(pay_form, text=label).pack(side="left", padx=(3, 2))
            if key == "debt":
                self.payment_debt_combo = ttk.Combobox(pay_form, textvariable=self.payment_vars[key], state="readonly", width=width)
                self.payment_debt_combo.pack(side="left", padx=(0, 6))
            else:
                ttk.Entry(pay_form, textvariable=self.payment_vars[key], width=width).pack(side="left", padx=(0, 6))
        ttk.Button(pay_form, text="Registrar pago", style="Accent.TButton", command=self.add_payment).pack(side="left", padx=4)
        ttk.Button(pay_form, text="Eliminar pago", style="Danger.TButton", command=self.delete_payment).pack(side="left", padx=4)
        self.payment_tree = ttk.Treeview(payments, columns=("date", "debt", "amount", "note"), show="headings", height=7)
        for col, label, width in [
            ("date", "Fecha", 95), ("debt", "Deuda", 145), ("amount", "Cantidad", 100), ("note", "Nota", 240),
        ]:
            self.payment_tree.heading(col, text=label)
            self.payment_tree.column(col, width=width, anchor="w" if col == "note" else "center")
        self.payment_tree.pack(fill="both", expand=True)

    def _build_graphs(self):
        toolbar = ttk.Frame(self.graphs_tab)
        toolbar.pack(fill="x", padx=5, pady=(4, 8))
        self.graph_type = tk.StringVar(value="Hábitos y bienestar")
        self.graph_period = tk.StringVar(value="30 días")
        ttk.Label(toolbar, text="Vista:").pack(side="left")
        ttk.Combobox(
            toolbar, textvariable=self.graph_type, state="readonly", width=26,
            values=["Hábitos y bienestar", "Avance académico", "Deudas: saldos", "Deudas: pagos del mes", "Pagos por mes"],
        ).pack(side="left", padx=5)
        ttk.Label(toolbar, text="Periodo:").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            toolbar, textvariable=self.graph_period, state="readonly", width=12,
            values=["7 días", "30 días", "90 días", "365 días"],
        ).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Actualizar gráfica", style="Accent.TButton", command=self.refresh_graphs).pack(side="left", padx=8)
        self.graph_canvas = tk.Canvas(self.graphs_tab, bg=COLORS["white"], highlightthickness=1, highlightbackground="#D6DFEA")
        self.graph_canvas.pack(fill="both", expand=True, padx=5, pady=3)
        self.graph_canvas.bind("<Configure>", lambda _event: self.refresh_graphs())

    def refresh_all(self):
        self.refresh_debts()
        self.refresh_history()
        self.refresh_panel()
        self.refresh_graphs()

    def refresh_panel(self):
        summary, pending_debt, recent, paid_week = self.db.dashboard()
        avg_compliance = sum(compliance(row) for row in recent) / len(recent) if recent else 0
        self.card_values["days"].configure(text=str(summary["days"]))
        self.card_values["compliance"].configure(text=f"{avg_compliance:.0f}%")
        self.card_values["energy"].configure(text=f"{summary['energy']:.1f}/10")
        self.card_values["debt"].configure(text=f"${pending_debt:,.2f}")
        self.week_tree.delete(*self.week_tree.get_children())
        metrics = [
            ("Cisco: submódulos", summary["cisco"]), ("Ejercicio: días", summary["exercise"]),
            ("Inglés: minutos", summary["english"]), ("Sueño promedio", f"{summary['sleep']:.1f} h"),
            ("Pagos de deuda", f"${paid_week:,.2f}"), ("Gastos evitados", f"${summary['avoided']:,.2f}"),
        ]
        for metric, value in metrics:
            self.week_tree.insert("", "end", values=(metric, value))
        self.recent_tree.delete(*self.recent_tree.get_children())
        for row in reversed(recent):
            self.recent_tree.insert("", "end", iid=row["entry_date"], values=(
                row["entry_date"], row["energy"] or "-", row["sleep_hours"] or "-",
                f"{compliance(row):.0f}%", row["note"],
            ))
        self.draw_chart(recent)

    def draw_chart(self, recent):
        self.chart.delete("all")
        width = max(self.chart.winfo_width(), 500)
        height = max(self.chart.winfo_height(), 210)
        self.chart.create_text(12, 12, anchor="nw", text="Energía (azul), sueño (verde), cumplimiento (ámbar)", fill=COLORS["muted"], font=("Segoe UI", 9))
        if not recent:
            self.chart.create_text(width / 2, height / 2, text="Todavía no hay datos para graficar.", fill=COLORS["muted"], font=("Segoe UI", 12))
            return
        left, top, right, bottom = 42, 38, width - 20, height - 30
        self.chart.create_line(left, bottom, right, bottom, fill="#D6DFEA")
        self.chart.create_line(left, top, left, bottom, fill="#D6DFEA")
        step = (right - left) / max(len(recent) - 1, 1)
        series = [
            ([row["energy"] for row in recent], 10, COLORS["blue"]),
            ([row["sleep_hours"] for row in recent], 10, COLORS["green"]),
            ([compliance(row) for row in recent], 100, COLORS["amber"]),
        ]
        for values, scale, color in series:
            points = []
            for index, value in enumerate(values):
                x = left + index * step
                y = bottom - (min(value, scale) / scale) * (bottom - top)
                points.extend((x, y))
                self.chart.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color)
            if len(points) >= 4:
                self.chart.create_line(*points, fill=color, width=2, smooth=True)
        for index, row in enumerate(recent):
            x = left + index * step
            self.chart.create_text(x, bottom + 13, text=row["entry_date"][5:], fill=COLORS["muted"], font=("Segoe UI", 8))

    def collect_entry(self):
        v = self.entry_vars
        debt_id = self.debt_lookup.get(v["debt_name"].get()) or None
        payment = parse_number(v["debt_payment"].get(), "Pago de deuda")
        if payment and not debt_id:
            raise ValueError("Selecciona una deuda antes de registrar un pago.")
        return {
            "entry_date": validate_date(self.entry_date.get()),
            "cisco_modules": parse_number(v["cisco_modules"].get(), "Cisco", int),
            "uveg_progress": parse_number(v["uveg_progress"].get(), "UVEG", float, 0, 100),
            "tuch_progress": parse_number(v["tuch_progress"].get(), "TUCH", float, 0, 100),
            "argos_minutes": parse_number(v["argos_minutes"].get(), "Argos", int),
            "centinela_minutes": parse_number(v["centinela_minutes"].get(), "Centinela", int),
            "exercise": 1 if v["exercise"].get() == "Sí" else 0,
            "english_minutes": parse_number(v["english_minutes"].get(), "Inglés", int),
            "debt_id": debt_id, "debt_payment": payment,
            "avoided_spending": parse_number(v["avoided_spending"].get(), "Gasto evitado"),
            "nofap": v["nofap"].get(),
            "sleep_hours": parse_number(v["sleep_hours"].get(), "Sueño", float, 0, 24),
            "energy": parse_number(v["energy"].get(), "Energía", int, 0, 10),
            "note": v["note"].get().strip(),
        }

    def save_entry(self):
        try:
            data = self.collect_entry()
            new_payment = data["debt_payment"]
            debt_id = data["debt_id"]
            data["debt_payment"] = 0
            self.db.save_entry(data)
            if new_payment:
                self.db.add_payment(debt_id, data["entry_date"], new_payment, "Registrado desde captura diaria")
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))
            return
        self.refresh_all()
        self.entry_vars["debt_payment"].set("")
        messagebox.showinfo("Registro guardado", f"Se guardó el día {self.entry_date.get()}.")

    def clear_entry(self):
        for key, variable in self.entry_vars.items():
            variable.set("No" if key == "exercise" else "")

    def load_entry(self):
        try:
            entry_date = validate_date(self.entry_date.get())
        except ValueError as exc:
            messagebox.showerror("Fecha inválida", str(exc))
            return
        row = self.db.get_entry(entry_date)
        self.clear_entry()
        if not row:
            return
        mapping = {
            "cisco_modules": row["cisco_modules"], "uveg_progress": row["uveg_progress"],
            "tuch_progress": row["tuch_progress"], "argos_minutes": row["argos_minutes"],
            "centinela_minutes": row["centinela_minutes"], "exercise": "Sí" if row["exercise"] else "No",
            "english_minutes": row["english_minutes"], "debt_name": next((name for name, debt_id in self.debt_lookup.items() if debt_id == row["debt_id"]), ""),
            "debt_payment": "", "avoided_spending": row["avoided_spending"],
            "nofap": row["nofap"], "sleep_hours": row["sleep_hours"], "energy": row["energy"], "note": row["note"],
        }
        for key, value in mapping.items():
            self.entry_vars[key].set("" if value in (0, 0.0, None) else value)

    def today_entry(self):
        self.entry_date.set(date.today().isoformat())
        self.load_entry()

    def refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        for row in self.db.list_entries():
            self.history_tree.insert("", "end", iid=row["entry_date"], values=(
                row["entry_date"], row["cisco_modules"], f"{row['uveg_progress']:g}", f"{row['tuch_progress']:g}",
                "Sí" if row["exercise"] else "No", row["english_minutes"], f"{row['sleep_hours']:g}",
                row["energy"] or "-", f"{compliance(row):.0f}%", f"${row['payments_on_date']:,.2f}", row["note"],
            ))

    def open_history(self, _event=None):
        selection = self.history_tree.selection()
        if selection:
            self.entry_date.set(selection[0])
            self.load_entry()
            self.tabs.select(self.entry_tab)

    def open_recent(self, _event=None):
        selection = self.recent_tree.selection()
        if selection:
            self.entry_date.set(selection[0])
            self.load_entry()
            self.tabs.select(self.entry_tab)

    def delete_history(self):
        selection = self.history_tree.selection()
        if not selection:
            return
        entry_date = selection[0]
        if messagebox.askyesno("Eliminar registro", f"¿Eliminar el registro de {entry_date}?"):
            self.db.delete_entry(entry_date)
            self.refresh_all()

    def refresh_debts(self):
        debts = self.db.list_debts()
        self.debt_lookup = {"": None, **{row["name"]: row["id"] for row in debts}}
        self.debt_combo.configure(values=list(self.debt_lookup))
        self.payment_debt_combo.configure(values=list(self.debt_lookup))
        self.debt_tree.delete(*self.debt_tree.get_children())
        for row in debts:
            if row["pending"] <= 0:
                status = "Liquidada"
            elif row["no_interest_payment"] and row["paid_month"] >= row["no_interest_payment"]:
                status = "Sin intereses ✓"
            elif row["minimum_payment"] and row["paid_month"] >= row["minimum_payment"]:
                status = "Mínimo cubierto"
            elif row["minimum_payment"]:
                status = f"Faltan ${row['minimum_payment'] - row['paid_month']:,.0f}"
            else:
                status = "Sin meta"
            self.debt_tree.insert("", "end", iid=str(row["id"]), values=(
                row["name"], f"${row['pending']:,.2f}", f"${row['paid_month']:,.2f}",
                f"${row['minimum_payment']:,.2f}", f"${row['no_interest_payment']:,.2f}",
                f"${row['monthly_goal']:,.2f}", status,
            ))
        self.payment_tree.delete(*self.payment_tree.get_children())
        for payment in self.db.list_payments():
            self.payment_tree.insert("", "end", iid=str(payment["id"]), values=(
                payment["payment_date"], payment["debt_name"], f"${payment['amount']:,.2f}", payment["note"],
            ))

    def save_debt(self):
        try:
            name = self.debt_vars["name"].get().strip()
            if not name:
                raise ValueError("Escribe el nombre de la deuda.")
            initial = parse_number(self.debt_vars["initial"].get(), "Saldo inicial")
            monthly = parse_number(self.debt_vars["monthly"].get(), "Meta mensual")
            minimum = parse_number(self.debt_vars["minimum"].get(), "Pago mínimo")
            no_interest = parse_number(self.debt_vars["no_interest"].get(), "Pago para no generar intereses")
            target = validate_date(self.debt_vars["target"].get(), allow_blank=True)
            self.db.save_debt(self.selected_debt_id, name, initial, monthly, minimum, no_interest, target)
        except (ValueError, sqlite3.IntegrityError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))
            return
        self.clear_debt_form()
        self.refresh_all()

    def select_debt(self, _event=None):
        selection = self.debt_tree.selection()
        if not selection:
            return
        self.selected_debt_id = int(selection[0])
        values = self.debt_tree.item(selection[0], "values")
        self.debt_vars["name"].set(values[0])
        row = next(row for row in self.db.list_debts() if row["id"] == self.selected_debt_id)
        self.debt_vars["initial"].set(f"{row['initial_balance']:g}")
        self.debt_vars["monthly"].set(f"{row['monthly_goal']:g}")
        self.debt_vars["minimum"].set(f"{row['minimum_payment']:g}")
        self.debt_vars["no_interest"].set(f"{row['no_interest_payment']:g}")
        self.debt_vars["target"].set(row["target_date"] or "")

    def clear_debt_form(self):
        self.selected_debt_id = None
        for variable in self.debt_vars.values():
            variable.set("")
        self.debt_tree.selection_remove(self.debt_tree.selection())

    def delete_debt(self):
        if not self.selected_debt_id:
            return
        if messagebox.askyesno("Eliminar deuda", "Los registros diarios conservarán sus datos, pero perderán la referencia a esta deuda. ¿Continuar?"):
            self.db.delete_debt(self.selected_debt_id)
            self.clear_debt_form()
            self.refresh_all()

    def add_payment(self):
        try:
            debt_id = self.debt_lookup.get(self.payment_vars["debt"].get())
            if not debt_id:
                raise ValueError("Selecciona una deuda.")
            payment_date = validate_date(self.payment_vars["date"].get())
            amount = parse_number(self.payment_vars["amount"].get(), "Cantidad", float, 0.01)
            self.db.add_payment(debt_id, payment_date, amount, self.payment_vars["note"].get().strip())
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo registrar el pago", str(exc))
            return
        self.payment_vars["amount"].set("")
        self.payment_vars["note"].set("")
        self.refresh_all()

    def delete_payment(self):
        selection = self.payment_tree.selection()
        if not selection:
            return
        if messagebox.askyesno("Eliminar pago", "¿Eliminar este movimiento de pago?"):
            self.db.delete_payment(int(selection[0]))
            self.refresh_all()

    def refresh_graphs(self):
        if not hasattr(self, "graph_canvas"):
            return
        canvas = self.graph_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 800)
        height = max(canvas.winfo_height(), 500)
        view = self.graph_type.get()
        days = int(self.graph_period.get().split()[0])
        if view == "Deudas: saldos":
            debts = self.db.list_debts()
            self.draw_bars(canvas, [(row["name"], row["pending"]) for row in debts], "Saldo pendiente por deuda", COLORS["red"], width, height, currency=True)
        elif view == "Deudas: pagos del mes":
            debts = self.db.list_debts()
            self.draw_grouped_debt_bars(canvas, debts, width, height)
        elif view == "Pagos por mes":
            rows = list(reversed(self.db.payments_by_month(12)))
            self.draw_bars(canvas, [(row["month"], row["amount"]) for row in rows], "Pagos totales por mes", COLORS["blue"], width, height, currency=True)
        else:
            entries = self.db.entries_for_period(days)
            if view == "Hábitos y bienestar":
                series = [
                    ("Energía", [row["energy"] for row in entries], 10, COLORS["blue"]),
                    ("Sueño", [row["sleep_hours"] for row in entries], 10, COLORS["green"]),
                    ("Cumplimiento", [compliance(row) / 10 for row in entries], 10, COLORS["amber"]),
                ]
                self.draw_lines(canvas, entries, series, "Hábitos y bienestar", width, height)
            else:
                series = [
                    ("Cisco", [row["cisco_modules"] for row in entries], None, COLORS["blue"]),
                    ("Inglés", [row["english_minutes"] for row in entries], None, COLORS["green"]),
                    ("Argos", [row["argos_minutes"] for row in entries], None, COLORS["amber"]),
                    ("Centinela", [row["centinela_minutes"] for row in entries], None, COLORS["red"]),
                ]
                self.draw_lines(canvas, entries, series, "Avance académico y técnico", width, height)

    def draw_empty(self, canvas, width, height):
        canvas.create_text(width / 2, height / 2, text="Todavía no hay datos para esta gráfica.", fill=COLORS["muted"], font=("Segoe UI", 13))

    def draw_bars(self, canvas, items, title, color, width, height, currency=False):
        canvas.create_text(25, 25, anchor="w", text=title, fill=COLORS["navy"], font=("Segoe UI", 16, "bold"))
        items = [(label, value) for label, value in items if label]
        if not items:
            return self.draw_empty(canvas, width, height)
        left, top, right, bottom = 170, 70, width - 50, height - 40
        maximum = max(value for _, value in items) or 1
        row_h = (bottom - top) / len(items)
        for index, (label, value) in enumerate(items):
            y = top + index * row_h + row_h / 2
            bar_end = left + (value / maximum) * (right - left)
            canvas.create_text(left - 10, y, anchor="e", text=label[:22], fill=COLORS["ink"])
            canvas.create_rectangle(left, y - 10, bar_end, y + 10, fill=color, outline="")
            shown = f"${value:,.2f}" if currency else f"{value:,.1f}"
            canvas.create_text(bar_end + 8, y, anchor="w", text=shown, fill=COLORS["ink"])

    def draw_grouped_debt_bars(self, canvas, debts, width, height):
        canvas.create_text(25, 25, anchor="w", text="Pagos del mes frente a metas", fill=COLORS["navy"], font=("Segoe UI", 16, "bold"))
        if not debts:
            return self.draw_empty(canvas, width, height)
        left, top, right, bottom = 170, 75, width - 50, height - 50
        maximum = max(max(row["paid_month"], row["minimum_payment"], row["no_interest_payment"], row["monthly_goal"]) for row in debts) or 1
        row_h = (bottom - top) / len(debts)
        colors = [COLORS["blue"], COLORS["amber"], COLORS["green"], COLORS["muted"]]
        labels = ["Pagado", "Mínimo", "Sin intereses", "Meta"]
        for index, row in enumerate(debts):
            base_y = top + index * row_h
            canvas.create_text(left - 10, base_y + row_h / 2, anchor="e", text=row["name"][:22], fill=COLORS["ink"])
            for j, value in enumerate((row["paid_month"], row["minimum_payment"], row["no_interest_payment"], row["monthly_goal"])):
                y = base_y + 8 + j * min(15, row_h / 5)
                canvas.create_rectangle(left, y, left + (value / maximum) * (right - left), y + 8, fill=colors[j], outline="")
        for j, label in enumerate(labels):
            x = left + j * 135
            canvas.create_rectangle(x, height - 25, x + 12, height - 13, fill=colors[j], outline="")
            canvas.create_text(x + 18, height - 19, anchor="w", text=label, fill=COLORS["ink"])

    def draw_lines(self, canvas, entries, series, title, width, height):
        canvas.create_text(25, 25, anchor="w", text=title, fill=COLORS["navy"], font=("Segoe UI", 16, "bold"))
        if not entries:
            return self.draw_empty(canvas, width, height)
        left, top, right, bottom = 55, 70, width - 35, height - 65
        canvas.create_line(left, bottom, right, bottom, fill="#D6DFEA")
        canvas.create_line(left, top, left, bottom, fill="#D6DFEA")
        step = (right - left) / max(len(entries) - 1, 1)
        overall_max = max(max(values or [0]) for _, values, _, _ in series) or 1
        for label, values, fixed_scale, color in series:
            scale = fixed_scale or overall_max
            points = []
            for index, value in enumerate(values):
                x = left + index * step
                y = bottom - (min(value, scale) / scale) * (bottom - top)
                points.extend((x, y))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, smooth=True)
            for index, value in enumerate(values):
                x, y = points[index * 2], points[index * 2 + 1]
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline=color)
        for index, entry in enumerate(entries):
            if index % max(1, len(entries) // 12) == 0:
                canvas.create_text(left + index * step, bottom + 15, text=entry["entry_date"][5:], fill=COLORS["muted"], font=("Segoe UI", 8))
        for index, (label, _, _, color) in enumerate(series):
            x = left + index * 145
            canvas.create_rectangle(x, height - 28, x + 12, height - 16, fill=color, outline="")
            canvas.create_text(x + 18, height - 22, anchor="w", text=label, fill=COLORS["ink"])


def self_test():
    with tempfile.TemporaryDirectory() as temp_dir:
        db = Database(Path(temp_dir) / "test.db")
        db.save_debt(None, "Tarjeta", 1000, 200, 100, 500, "2026-12-31")
        debt = db.list_debts()[0]
        db.save_entry({
            "entry_date": "2026-06-12", "cisco_modules": 2, "uveg_progress": 10,
            "tuch_progress": 5, "argos_minutes": 30, "centinela_minutes": 0,
            "exercise": 1, "english_minutes": 20, "debt_id": debt["id"],
            "debt_payment": 0, "avoided_spending": 50, "nofap": "Cumplido",
            "sleep_hours": 7.5, "energy": 8, "note": "Prueba",
        })
        assert db.get_entry("2026-06-12")["energy"] == 8
        db.add_payment(debt["id"], date.today().isoformat(), 150, "Pago 1")
        db.add_payment(debt["id"], date.today().isoformat(), 75, "Pago 2")
        current = db.list_debts()[0]
        assert current["pending"] == 775
        assert current["paid_month"] == 225
        assert len(db.list_payments()) == 2
        assert len(db.list_entries()) == 1
        db.delete_entry("2026-06-12")
        assert len(db.list_entries()) == 0
        db.close()
    with tempfile.TemporaryDirectory() as temp_dir:
        legacy_path = Path(temp_dir) / "legacy.db"
        legacy = sqlite3.connect(legacy_path)
        legacy.executescript(
            """
            CREATE TABLE debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                initial_balance REAL NOT NULL DEFAULT 0, monthly_goal REAL NOT NULL DEFAULT 0,
                target_date TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE daily_entries (
                entry_date TEXT PRIMARY KEY, cisco_modules INTEGER NOT NULL DEFAULT 0,
                uveg_progress REAL NOT NULL DEFAULT 0, tuch_progress REAL NOT NULL DEFAULT 0,
                argos_minutes INTEGER NOT NULL DEFAULT 0, centinela_minutes INTEGER NOT NULL DEFAULT 0,
                exercise INTEGER NOT NULL DEFAULT 0, english_minutes INTEGER NOT NULL DEFAULT 0,
                debt_id INTEGER, debt_payment REAL NOT NULL DEFAULT 0, avoided_spending REAL NOT NULL DEFAULT 0,
                nofap TEXT NOT NULL DEFAULT '', sleep_hours REAL NOT NULL DEFAULT 0,
                energy INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO debts (name, initial_balance) VALUES ('Legacy', 500);
            INSERT INTO daily_entries (entry_date, debt_id, debt_payment) VALUES ('2026-05-20', 1, 80);
            """
        )
        legacy.commit()
        legacy.close()
        migrated = Database(legacy_path)
        assert len(migrated.list_payments()) == 1
        assert migrated.list_debts()[0]["pending"] == 420
        assert migrated.get_entry("2026-05-20")["debt_payment"] == 0
        migrated.close()
    print("SELF-TEST OK")


def ui_smoke_test():
    with tempfile.TemporaryDirectory() as temp_dir:
        db = Database(Path(temp_dir) / "test.db")
        app = BitacoraApp(db)
        app.update_idletasks()
        app.update()
        app.destroy()
        db.close()
    print("UI-SMOKE-TEST OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif "--ui-smoke-test" in sys.argv:
        ui_smoke_test()
    else:
        BitacoraApp(Database()).mainloop()
