"""Offline E2E server: the production app and database run only in the test process."""
from backend.app.main import app
from backend.app.source_reader import SourceReader

SourceReader.resolve_revision = lambda self, repo, ref=None: {
    'commit_sha':'a'*40, 'status':'resolved', 'note':'synthetic offline E2E revision'}
