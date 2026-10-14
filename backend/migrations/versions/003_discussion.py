"""Add discussion sessions; preserve old messages in explicit legacy sessions."""
from alembic import op
import sqlalchemy as sa
import json,uuid
revision='003'
down_revision='002'
def upgrade():
    op.create_table('conversations',sa.Column('workspace_id',sa.String(),sa.ForeignKey('workspaces.id'),nullable=False),sa.Column('id',sa.String(),primary_key=True),sa.Column('created_at',sa.String(),nullable=False),sa.Column('surface',sa.String(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('data',sa.JSON(),nullable=False),sa.Column('updated_at',sa.String(),nullable=False),sa.Column('deleted_at',sa.String(),nullable=True))
    db=op.get_bind()
    # FTS5 trigram handles Chinese substrings; explicit keyword fallback if unavailable.
    try:db.exec_driver_sql("CREATE VIRTUAL TABLE discussion_fts USING fts5(message_id UNINDEXED, conversation_id UNINDEXED, workspace_id UNINDEXED, content, tokenize='trigram')")
    except sa.exc.OperationalError:pass
    rows=db.execute(sa.text('SELECT id,workspace_id,created_at,proposal FROM messages ORDER BY created_at,id')).mappings().all()
    sessions={}
    for row in rows:
        wid=row['workspace_id']
        if wid not in sessions:
            cid=uuid.uuid4().hex;sessions[wid]=cid
            db.execute(sa.text('INSERT INTO conversations VALUES (:w,:i,:t,:s,0,:d,:t,NULL)'),{'w':wid,'i':cid,'t':row['created_at'],'s':'legacy','d':json.dumps({'migration':'source surface unknown; not treated as completed turns'})})
        meta=json.loads(row['proposal'] or '{}');meta['discussion']={'conversation_id':sessions[wid],'status':'legacy','sequence':0}
        db.execute(sa.text('UPDATE messages SET proposal=:p WHERE id=:i'),{'p':json.dumps(meta),'i':row['id']})
def downgrade():
    raise RuntimeError('Discussion data migration is forward-only; export before explicit rollback')
