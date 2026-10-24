-- 0003 M2: keep a summary of the AI extraction on the upload (mode, model, steps, problems).

ALTER TABLE framework_upload ADD COLUMN extraction TEXT CHECK (extraction IS NULL OR json_valid(extraction));
