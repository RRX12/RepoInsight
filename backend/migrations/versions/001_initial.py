"""Initial constrained schema."""
from alembic import op
from pathlib import Path
revision = '001'
down_revision = None
def upgrade():
    # Frozen SQL; future model edits cannot silently change migration 001.
    for statement in Path(__file__).with_name('schema_v1.sql').read_text(encoding='utf-8').split(';'):
        if statement.strip(): op.execute(statement)
def downgrade():
    for table in ['memory_events','experiments','attempts','contributions','artifacts','messages','improvements','findings','evidence','runs','snapshots','jd_versions','workspaces']:
        op.drop_table(table)
