ALTER TABLE tasks ADD COLUMN minio_url VARCHAR(500);
CREATE INDEX idx_task_minio_url ON tasks(minio_url);