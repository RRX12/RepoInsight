CREATE TABLE workspaces (
	interest TEXT NOT NULL, 
	role TEXT NOT NULL, 
	skills TEXT NOT NULL, 
	time_budget TEXT NOT NULL, 
	environment TEXT NOT NULL, 
	stage VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE jd_versions (
	raw_text TEXT NOT NULL, 
	requirements JSON NOT NULL, 
	version INTEGER NOT NULL, 
	supersedes_id VARCHAR, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, version), 
	FOREIGN KEY(supersedes_id) REFERENCES jd_versions (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_jd_versions_workspace_id ON jd_versions (workspace_id);

CREATE TABLE messages (
	role VARCHAR NOT NULL, 
	content TEXT NOT NULL, 
	proposal JSON NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_messages_workspace_id ON messages (workspace_id);

CREATE TABLE runs (
	status VARCHAR NOT NULL, 
	request JSON NOT NULL, 
	steps JSON NOT NULL, 
	result JSON NOT NULL, 
	error TEXT, 
	idempotency_key VARCHAR NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, idempotency_key), 
	CHECK (status IN ('queued','running','completed','failed','cancelled','interrupted')), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_runs_workspace_id ON runs (workspace_id);

CREATE TABLE snapshots (
	owner VARCHAR NOT NULL, 
	repo VARCHAR NOT NULL, 
	commit_sha VARCHAR NOT NULL, 
	metadata_json JSON NOT NULL, 
	coverage JSON NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_snapshots_workspace_id ON snapshots (workspace_id);

CREATE TABLE artifacts (
	type VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	jd_version_id VARCHAR, 
	dependency_ids JSON NOT NULL, 
	claims JSON NOT NULL, 
	review_status VARCHAR NOT NULL, 
	idempotency_key VARCHAR NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, idempotency_key), 
	CHECK (type IN ('task_pack','resume','interview_notes')), 
	CHECK (review_status IN ('current','needs_review')), 
	FOREIGN KEY(jd_version_id) REFERENCES jd_versions (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_artifacts_workspace_id ON artifacts (workspace_id);

CREATE TABLE evidence (
	type VARCHAR NOT NULL, 
	source_ref TEXT NOT NULL, 
	snapshot_id VARCHAR, 
	path TEXT, 
	line_start INTEGER, 
	line_end INTEGER, 
	excerpt TEXT NOT NULL, 
	content_hash VARCHAR NOT NULL, 
	provenance VARCHAR NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (type IN ('source_code','readme','user_statement','diff','test_report','external_analysis')), 
	FOREIGN KEY(snapshot_id) REFERENCES snapshots (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_evidence_workspace_id ON evidence (workspace_id);

CREATE TABLE findings (
	snapshot_id VARCHAR NOT NULL, 
	claim TEXT NOT NULL, 
	kind VARCHAR NOT NULL, 
	evidence_ids JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	coverage_note TEXT NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (kind IN ('upstream_capability','problem','hypothesis')), 
	CHECK (status IN ('supported','unverified','disputed','stale')), 
	FOREIGN KEY(snapshot_id) REFERENCES snapshots (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_findings_workspace_id ON findings (workspace_id);

CREATE TABLE improvements (
	jd_version_id VARCHAR, 
	snapshot_id VARCHAR, 
	details JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (status IN ('proposed','selected','stale','abandoned')), 
	FOREIGN KEY(jd_version_id) REFERENCES jd_versions (id), 
	FOREIGN KEY(snapshot_id) REFERENCES snapshots (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_improvements_workspace_id ON improvements (workspace_id);

CREATE TABLE memory_events (
	entity_type VARCHAR NOT NULL, 
	entity_id VARCHAR NOT NULL, 
	operation VARCHAR NOT NULL, 
	"before" JSON NOT NULL, 
	"after" JSON NOT NULL, 
	source_message_id VARCHAR, 
	supersedes_event_id VARCHAR, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_message_id) REFERENCES messages (id), 
	FOREIGN KEY(supersedes_event_id) REFERENCES memory_events (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_memory_events_workspace_id ON memory_events (workspace_id);

CREATE TABLE contributions (
	improvement_id VARCHAR, 
	personal_role TEXT NOT NULL, 
	problem TEXT NOT NULL, 
	action TEXT NOT NULL, 
	tradeoffs TEXT NOT NULL, 
	outcome TEXT NOT NULL, 
	state VARCHAR NOT NULL, 
	evidence_ids JSON NOT NULL, 
	verification JSON NOT NULL, 
	version INTEGER NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (state IN ('proposed','in_progress','implemented','validated','abandoned')), 
	FOREIGN KEY(improvement_id) REFERENCES improvements (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_contributions_workspace_id ON contributions (workspace_id);

CREATE TABLE attempts (
	contribution_id VARCHAR NOT NULL, 
	details JSON NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contribution_id) REFERENCES contributions (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_attempts_workspace_id ON attempts (workspace_id);

CREATE TABLE experiments (
	contribution_id VARCHAR NOT NULL, 
	details JSON NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	created_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contribution_id) REFERENCES contributions (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX ix_experiments_workspace_id ON experiments (workspace_id);