ALTER TABLE staff_accounts ADD COLUMN deletable boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS import_rows_record_source_idx ON import_rows(record_id,id);
