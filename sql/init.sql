-- Jobs tracking table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    filename VARCHAR(255) NOT NULL,
    blob_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    error_message TEXT,
    records_processed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- Sales records table
CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    product_id INTEGER NOT NULL CHECK (product_id > 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    total NUMERIC(14,2) NOT NULL CHECK (total >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
CREATE INDEX IF NOT EXISTS idx_sales_product_id ON sales(product_id);

-- Daily summary table (populated by n8n workflow)
CREATE TABLE IF NOT EXISTS sales_daily_summary (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    total_sales NUMERIC(16,2) NOT NULL,
    record_count INTEGER NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
