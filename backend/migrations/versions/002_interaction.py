"""Additive editor/metric state; existing facts, contributions and artifacts reused."""
from alembic import op
import sqlalchemy as sa
revision='002'
down_revision='001'
def upgrade():
    op.create_table('interaction_states',sa.Column('workspace_id',sa.String(),sa.ForeignKey('workspaces.id'),primary_key=True),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('data',sa.JSON(),nullable=False))
    op.create_index('uq_interaction_receipt','memory_events',['workspace_id','entity_id'],unique=True,sqlite_where=sa.text("entity_type = 'interaction_receipt'"))
def downgrade():
    op.drop_index('uq_interaction_receipt',table_name='memory_events')
    op.drop_table('interaction_states')
