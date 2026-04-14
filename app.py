from __future__ import annotations

import os
import secrets
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.middleware.proxy_fix import ProxyFix

from sqlalchemy import text



#BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

database_url = os.getenv("DATABASE_URL")

print("DATABASE_URL configured:", bool(database_url))
print("DB target:", database_url.split("@")[-1] if database_url else "missing")

if not database_url:
    # lokaalia kehitystä varten
    database_url = "sqlite:///app.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy()

WEEKLY_GOAL_KM = 15.0
MONTHLY_GOAL_KM = 60.0
DEFAULT_AVATARS = ["🏃", "🦊", "🐺", "🐻", "🦁", "🐼", "🐯", "🦄", "🐸", "🐙", "🐧", "🐵"]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PREFERRED_URL_SCHEME = "https"
    SEED_DEMO_DATA = os.environ.get("SEED_DEMO_DATA", "false").lower() == "true"

    raw_database_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
    if raw_database_url and raw_database_url.startswith("postgres://"):
        raw_database_url = raw_database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = raw_database_url or f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        if app.config["SEED_DEMO_DATA"]:
            seed_demo_data()

    register_routes(app)
    register_cli(app)
    

    @app.get("/debug-db")
    def debug_db():
        try:
            tables = db.session.execute(text("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)).mappings().all()

            participants_count = None
            runs_count = None
            latest_runs = []

            try:
                participants_count = db.session.execute(
                    text("SELECT COUNT(*) FROM participants")
                ).scalar()
            except Exception as e:
                participants_count = f"participants query failed: {e}"

            try:
                runs_count = db.session.execute(
                    text("SELECT COUNT(*) FROM runs")
                ).scalar()
            except Exception as e:
                runs_count = f"runs query failed: {e}"

            try:
                latest_runs = db.session.execute(text("""
                    SELECT *
                    FROM runs
                    ORDER BY created_at DESC
                    LIMIT 5
                """)).mappings().all()
                latest_runs = [dict(r) for r in latest_runs]
            except Exception as e:
                latest_runs = [f"latest_runs query failed: {e}"]
    
            return {
                "tables": [dict(t) for t in tables],
                "participants_count": participants_count,
                "runs_count": runs_count,
                "latest_runs": latest_runs,
            }
        except Exception as e:
            return {"error": str(e)}, 500

    return app


class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    display_name = db.Column(db.String(80), nullable=False)
    normalized_name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    avatar = db.Column(db.String(8), nullable=False, default="🏃")
    edit_token = db.Column(db.String(64), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(24))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    runs = db.relationship("RunEntry", back_populates="participant", cascade="all, delete-orphan")


class RunEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=False, index=True)
    run_date = db.Column(db.Date, nullable=False, index=True)
    distance_km = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(160), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    participant = db.relationship("Participant", back_populates="runs")


@dataclass
class WeekSummary:
    label: str
    start: date
    end: date
    km: float
    hit_goal: bool


@dataclass
class ParticipantDashboard:
    participant: Participant
    week_km: float
    month_km: float
    all_time_km: float
    week_remaining: float
    month_remaining: float
    current_streak: int
    history: List[WeekSummary]
    owns_profile: bool
    leaderboard_pct: float


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def build_week_history(entries: List[RunEntry], weeks: int = 6) -> List[WeekSummary]:
    today = date.today()
    current_week_start = week_start(today)
    km_by_week: Dict[date, float] = defaultdict(float)

    for entry in entries:
        km_by_week[week_start(entry.run_date)] += float(entry.distance_km)

    history: List[WeekSummary] = []
    for i in range(weeks):
        start = current_week_start - timedelta(days=7 * i)
        end = start + timedelta(days=6)
        km = round(km_by_week.get(start, 0.0), 1)
        history.append(
            WeekSummary(
                label=f"vko {start.isocalendar().week}",
                start=start,
                end=end,
                km=km,
                hit_goal=km >= WEEKLY_GOAL_KM,
            )
        )
    return history


def compute_current_streak(history: List[WeekSummary]) -> int:
    streak = 0
    for item in history:
        if item.hit_goal:
            streak += 1
        else:
            break
    return streak


def cookie_owner_public_id() -> Optional[str]:
    token = request.cookies.get("runner_token")
    if not token:
        return None
    participant = Participant.query.filter_by(edit_token=token, is_active=True).first()
    return participant.public_id if participant else None


def set_runner_cookie(response, participant: Participant):
    response.set_cookie(
        "runner_token",
        participant.edit_token,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="Lax",
        secure=not current_app_debug(),
    )
    return response


def current_app_debug() -> bool:
    return os.environ.get("FLASK_DEBUG", "0") in {"1", "true", "True"}


def dashboard_data() -> List[ParticipantDashboard]:
    participants = Participant.query.filter_by(is_active=True).order_by(Participant.display_name.asc()).all()
    today = date.today()
    ws = week_start(today)
    ms = month_start(today)
    owner_public_id = cookie_owner_public_id()

    all_runs = (
        RunEntry.query.join(Participant)
        .filter(Participant.is_active.is_(True))
        .order_by(RunEntry.run_date.desc(), RunEntry.created_at.desc())
        .all()
    )

    runs_by_pid: Dict[int, List[RunEntry]] = defaultdict(list)
    for run in all_runs:
        runs_by_pid[run.participant_id].append(run)

    totals = []
    for p in participants:
        entries = runs_by_pid.get(p.id, [])
        week_km = round(sum(r.distance_km for r in entries if ws <= r.run_date <= today), 1)
        month_km = round(sum(r.distance_km for r in entries if ms <= r.run_date <= today), 1)
        all_time_km = round(sum(r.distance_km for r in entries), 1)
        history = build_week_history(entries)
        totals.append(
            (
                p.id,
                all_time_km,
                ParticipantDashboard(
                    participant=p,
                    week_km=week_km,
                    month_km=month_km,
                    all_time_km=all_time_km,
                    week_remaining=round(max(0.0, WEEKLY_GOAL_KM - week_km), 1),
                    month_remaining=round(max(0.0, MONTHLY_GOAL_KM - month_km), 1),
                    current_streak=compute_current_streak(history),
                    history=history,
                    owns_profile=(owner_public_id == p.public_id),
                    leaderboard_pct=0.0,
                ),
            )
        )

    max_total = max([total for _, total, _ in totals], default=0.0)
    result: List[ParticipantDashboard] = []
    for _, total, dash in sorted(totals, key=lambda x: (-x[1], x[2].participant.display_name.lower())):
        dash.leaderboard_pct = 0.0 if max_total <= 0 else round((total / max_total) * 100.0, 1)
        result.append(dash)
    return result


def recent_runs(limit: int = 10) -> List[RunEntry]:
    return (
        RunEntry.query.join(Participant)
        .filter(Participant.is_active.is_(True))
        .order_by(RunEntry.run_date.desc(), RunEntry.created_at.desc())
        .limit(limit)
        .all()
    )


def seed_demo_data() -> None:
    if Participant.query.count() > 0:
        return

    demo_people = [
        ("Matti", "🐺"),
        ("Laura", "🦊"),
        ("Otso", "🐻"),
    ]
    participants: List[Participant] = []
    for name, avatar in demo_people:
        participant = Participant(
            display_name=name,
            normalized_name=normalize_name(name),
            avatar=avatar,
        )
        db.session.add(participant)
        participants.append(participant)

    db.session.flush()

    today = date.today()
    sample_runs = [
        (participants[0], today - timedelta(days=1), 8.0, "Kevyt iltalenkki"),
        (participants[0], today - timedelta(days=4), 9.5, "Pitkä peruslenkki"),
        (participants[1], today - timedelta(days=2), 6.0, "Palauttava"),
        (participants[1], today - timedelta(days=8), 12.0, "Viikon päälenkki"),
        (participants[2], today - timedelta(days=3), 16.0, "Tavoite pakettiin"),
        (participants[2], today - timedelta(days=11), 10.0, "Tasainen veto"),
        (participants[2], today - timedelta(days=18), 15.0, "Hyvä flow"),
    ]
    for participant, run_day, km, note in sample_runs:
        db.session.add(RunEntry(participant_id=participant.id, run_date=run_day, distance_km=km, note=note))
    db.session.commit()


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Seed local demo data once."""
        seed_demo_data()
        print("Demo data seeded.")



def register_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        dashboards = dashboard_data()
        archived = Participant.query.filter_by(is_active=False).order_by(Participant.display_name.asc()).all()
        response = make_response(
            render_template(
                "index.html",
                dashboards=dashboards,
                recent_entries=recent_runs(),
                weekly_goal=WEEKLY_GOAL_KM,
                monthly_goal=MONTHLY_GOAL_KM,
                avatar_choices=DEFAULT_AVATARS,
                archived=archived,
            )
        )
        return response

    @app.get("/health")
    def health():
        db.session.execute(db.text("SELECT 1"))
        return {"ok": True, "database": "reachable"}, 200

    @app.post("/participants")
    def create_participant():
        display_name = request.form.get("display_name", "").strip()
        avatar = request.form.get("avatar", "🏃").strip() or "🏃"

        if not display_name:
            flash("Anna käyttäjälle nimi.", "error")
            return redirect(url_for("index"))

        normalized = normalize_name(display_name)
        existing = Participant.query.filter(func.lower(Participant.normalized_name) == normalized).first()
        if existing:
            flash(f"Käyttäjä '{existing.display_name}' on jo olemassa.", "error")
            return redirect(url_for("index"))

        if avatar not in DEFAULT_AVATARS:
            avatar = "🏃"

        participant = Participant(
            display_name=display_name,
            normalized_name=normalized,
            avatar=avatar,
        )
        db.session.add(participant)
        db.session.commit()

        response = make_response(redirect(url_for("index")))
        set_runner_cookie(response, participant)
        flash(f"Osallistuja {participant.display_name} lisätty.", "success")
        return response

    @app.post("/participants/<public_id>/claim")
    def claim_participant(public_id: str):
        participant = Participant.query.filter_by(public_id=public_id, is_active=True).first_or_404()
        response = make_response(redirect(url_for("index")))
        set_runner_cookie(response, participant)
        flash(f"Valittu aktiiviseksi käyttäjäksi: {participant.display_name}", "success")
        return response

    @app.post("/runs")
    def create_run():
        participant_public_id = request.form.get("participant_public_id", "").strip()
        participant = Participant.query.filter_by(public_id=participant_public_id, is_active=True).first()
        if not participant:
            flash("Valitse kelvollinen osallistuja.", "error")
            return redirect(url_for("index"))

        cookie_token = request.cookies.get("runner_token")
        if cookie_token != participant.edit_token:
            flash("Voit lisätä kilometrejä vain valitulle omalle profiilillesi.", "error")
            return redirect(url_for("index"))

        try:
            km = float(request.form.get("distance_km", "0").replace(",", "."))
        except ValueError:
            flash("Kilometrimäärä ei ollut kelvollinen numero.", "error")
            return redirect(url_for("index"))

        if km <= 0 or km > 200:
            flash("Kilometrimäärän pitää olla välillä 0.1–200.", "error")
            return redirect(url_for("index"))

        run_date_raw = request.form.get("run_date", "")
        try:
            run_day = datetime.strptime(run_date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Päivämäärä puuttuu tai on virheellinen.", "error")
            return redirect(url_for("index"))

        note = request.form.get("note", "").strip()[:160]

        run = RunEntry(participant_id=participant.id, run_date=run_day, distance_km=km, note=note or None)
        db.session.add(run)
        db.session.commit()
        flash(f"Lisättiin {km:.1f} km käyttäjälle {participant.display_name}.", "success")
        return redirect(url_for("index"))

    @app.post("/participants/<public_id>/archive")
    def archive_participant(public_id: str):
        participant = Participant.query.filter_by(public_id=public_id, is_active=True).first_or_404()
        if request.cookies.get("runner_token") != participant.edit_token:
            flash("Vain oman profiilin voi arkistoida tässä kevyessä versiossa.", "error")
            return redirect(url_for("index"))

        participant.is_active = False
        db.session.commit()
        response = make_response(redirect(url_for("index")))
        response.delete_cookie("runner_token")
        flash(f"Käyttäjä {participant.display_name} arkistoitiin.", "success")
        return response

    @app.post("/participants/<public_id>/restore")
    def restore_participant(public_id: str):
        participant = Participant.query.filter_by(public_id=public_id, is_active=False).first_or_404()
        participant.is_active = True
        db.session.commit()
        flash(f"Käyttäjä {participant.display_name} palautettiin.", "success")
        return redirect(url_for("index"))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
