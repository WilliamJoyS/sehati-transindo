CREATE TABLE IF NOT EXISTS customers (
 id uuid PRIMARY KEY, code text NOT NULL UNIQUE, name text NOT NULL,
 active boolean NOT NULL DEFAULT true, data_version bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS billing_documents (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customers(id),
 invoice_number text NOT NULL, period_start date NOT NULL, period_end date NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(customer_id,invoice_number),
 CHECK(period_end >= period_start), UNIQUE(id,customer_id)
);
CREATE TABLE IF NOT EXISTS deliveries (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customers(id),
 source_document_id uuid NOT NULL, do_number text NOT NULL, vehicle_plate text NOT NULL,
 transporter text, load_date date NOT NULL, estimated_unload_date date, actual_unload_date date,
 origin text, destination text, distributor text, capacity_m3 numeric(18,6), vehicle_type text,
 quantity bigint, volume_m3 numeric(18,6), notes text, version bigint NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(source_document_id,customer_id) REFERENCES billing_documents(id,customer_id),
 CHECK(quantity IS NULL OR quantity>=0), CHECK(capacity_m3 IS NULL OR capacity_m3>=0),
 CHECK(volume_m3 IS NULL OR volume_m3>=0), UNIQUE(id,customer_id)
);
CREATE INDEX IF NOT EXISTS deliveries_customer_date ON deliveries(customer_id,load_date,id);
CREATE TABLE IF NOT EXISTS invoice_lines (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customers(id),
 billing_document_id uuid NOT NULL, delivery_id uuid, normal_charge numeric(18,2),
 additional_charge numeric(18,2), reported_total numeric(18,2), note text,
 version bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(billing_document_id,customer_id) REFERENCES billing_documents(id,customer_id),
 FOREIGN KEY(delivery_id,customer_id) REFERENCES deliveries(id,customer_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS invoice_line_delivery ON invoice_lines(delivery_id) WHERE delivery_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS import_batches (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customers(id), staff_id uuid REFERENCES staff_accounts(id),
 filename text NOT NULL, file_digest text NOT NULL, mapping_version text NOT NULL,
 status text NOT NULL CHECK(status IN ('preview','blocked','committed','failed')),
 revision integer NOT NULL DEFAULT 1, report jsonb NOT NULL, staged jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), committed_at timestamptz
);
CREATE INDEX IF NOT EXISTS import_customer_digest ON import_batches(customer_id,file_digest,mapping_version);
CREATE TABLE IF NOT EXISTS import_rows (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, batch_id uuid NOT NULL REFERENCES import_batches(id),
 sheet text NOT NULL, row_number integer NOT NULL, kind text NOT NULL,
 record_id uuid, action text NOT NULL, source_payload jsonb NOT NULL,
 before_payload jsonb, after_payload jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS legacy_document_snapshots (
 customer_id uuid NOT NULL REFERENCES customers(id), invoice_number text NOT NULL,
 content_digest text NOT NULL, batch_id uuid NOT NULL REFERENCES import_batches(id),
 PRIMARY KEY(customer_id,invoice_number,content_digest)
);
