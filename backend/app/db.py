import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, String, Text, Integer, ForeignKey, JSON, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()
DATA = Path(os.getenv('REPOCAREER_DATA', './data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
engine = create_engine(f'sqlite:///{DATA / "repocareer.db"}', connect_args={'check_same_thread': False, 'timeout': 20})
@event.listens_for(engine, 'connect')
def configure(conn, _):
    # Disable sqlite3 legacy transaction control: SELECT must share one snapshot
    # with all other reads in the workspace response.
    conn.isolation_level = None
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
@event.listens_for(engine, 'begin')
def begin_transaction(conn):
    conn.exec_driver_sql('BEGIN')
Session = sessionmaker(engine, expire_on_commit=False)
def uid(): return uuid.uuid4().hex
def now(): return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase): pass
class Record:
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    created_at: Mapped[str] = mapped_column(String, default=now)
class Workspace(Record, Base):
    __tablename__ = 'workspaces'
    interest: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default='Python 开发')
    skills: Mapped[str] = mapped_column(Text, default='')
    time_budget: Mapped[str] = mapped_column(Text, default='')
    environment: Mapped[str] = mapped_column(Text, default='')
    stage: Mapped[str] = mapped_column(String, default='understanding')
class Scoped(Record):
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'), index=True)
class JD(Scoped, Base):
    __tablename__ = 'jd_versions'
    raw_text: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('jd_versions.id'))
    __table_args__ = (UniqueConstraint('workspace_id', 'version'),)
class Snapshot(Scoped, Base):
    __tablename__ = 'snapshots'
    owner: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    commit_sha: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
class Evidence(Scoped, Base):
    __tablename__ = 'evidence'
    type: Mapped[str] = mapped_column(String)
    source_ref: Mapped[str] = mapped_column(Text, default='')
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey('snapshots.id'))
    path: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)
    provenance: Mapped[str] = mapped_column(String)
    __table_args__ = (CheckConstraint("type IN ('source_code','readme','user_statement','diff','test_report','external_analysis')"),)
class Finding(Scoped, Base):
    __tablename__ = 'findings'
    snapshot_id: Mapped[str] = mapped_column(ForeignKey('snapshots.id'))
    claim: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default='unverified')
    coverage_note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (CheckConstraint("kind IN ('upstream_capability','problem','hypothesis')"), CheckConstraint("status IN ('supported','unverified','disputed','stale')"))
class Improvement(Scoped, Base):
    __tablename__ = 'improvements'
    jd_version_id: Mapped[str | None] = mapped_column(ForeignKey('jd_versions.id'))
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey('snapshots.id'))
    details: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default='proposed')
    __table_args__ = (CheckConstraint("status IN ('proposed','selected','stale','abandoned')"),)
class Contribution(Scoped, Base):
    __tablename__ = 'contributions'
    improvement_id: Mapped[str | None] = mapped_column(ForeignKey('improvements.id'))
    personal_role: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text, default='')
    action: Mapped[str] = mapped_column(Text)
    tradeoffs: Mapped[str] = mapped_column(Text, default='')
    outcome: Mapped[str] = mapped_column(Text, default='')
    state: Mapped[str] = mapped_column(String)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint("state IN ('proposed','in_progress','implemented','validated','abandoned')"),)
class Attempt(Scoped, Base):
    __tablename__ = 'attempts'
    contribution_id: Mapped[str] = mapped_column(ForeignKey('contributions.id'))
    details: Mapped[dict] = mapped_column(JSON)
class Experiment(Scoped, Base):
    __tablename__ = 'experiments'
    contribution_id: Mapped[str] = mapped_column(ForeignKey('contributions.id'))
    details: Mapped[dict] = mapped_column(JSON)
class Message(Scoped, Base):
    __tablename__ = 'messages'
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
class MemoryEvent(Scoped, Base):
    __tablename__ = 'memory_events'
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    operation: Mapped[str] = mapped_column(String)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey('messages.id'))
    supersedes_event_id: Mapped[str | None] = mapped_column(ForeignKey('memory_events.id'))
class Artifact(Scoped, Base):
    __tablename__ = 'artifacts'
    type: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    jd_version_id: Mapped[str | None] = mapped_column(ForeignKey('jd_versions.id'))
    dependency_ids: Mapped[list] = mapped_column(JSON, default=list)
    claims: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String, default='current')
    idempotency_key: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint('workspace_id','idempotency_key'), CheckConstraint("type IN ('task_pack','resume','interview_notes')"), CheckConstraint("review_status IN ('current','needs_review')"))
class Run(Scoped, Base):
    __tablename__ = 'runs'
    status: Mapped[str] = mapped_column(String, default='queued')
    request: Mapped[dict] = mapped_column(JSON)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint('workspace_id','idempotency_key'), CheckConstraint("status IN ('queued','running','completed','failed','cancelled','interrupted')"))
class InteractionState(Base):
    __tablename__ = 'interaction_states'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'),primary_key=True)
    revision: Mapped[int] = mapped_column(Integer,default=0)
    data: Mapped[dict] = mapped_column(JSON,default=dict)

def asdict(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}

def migrate():
    from alembic.config import Config
    from alembic import command
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    cfg.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    command.upgrade(cfg, 'head')
