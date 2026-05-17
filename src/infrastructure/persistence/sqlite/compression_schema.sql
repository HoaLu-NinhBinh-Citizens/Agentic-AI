-- Compression Module Database Schema
-- Phase 4E - Production Fixes (v4.6)
-- Addresses: Atomicity, Redis Lock Security, Real LRU, CPU Guards,
--            Batch Processing, Deduplication, Integrity Scanner, etc.

-- ============================================================================
-- Extended memory table with compression fields
-- ============================================================================

ALTER TABLE memory ADD COLUMN compressed BOOLEAN DEFAULT FALSE;
ALTER TABLE memory ADD COLUMN compression_type TEXT;
ALTER TABLE memory ADD COLUMN compression_metadata JSON;
ALTER TABLE memory ADD COLUMN original_blob_id INTEGER REFERENCES original_blobs(id);
ALTER TABLE memory ADD COLUMN original_length INTEGER;
ALTER TABLE memory ADD COLUMN compressed_length INTEGER;
ALTER TABLE memory ADD COLUMN semantic_similarity REAL DEFAULT 0.0;
ALTER TABLE memory ADD COLUMN last_compressed_at INTEGER;
ALTER TABLE memory ADD COLUMN compression_attempt_count INTEGER DEFAULT 0;
ALTER TABLE memory ADD COLUMN no_compress BOOLEAN DEFAULT FALSE;
-- Issue #7: TTL-based no-compress re-evaluation
ALTER TABLE memory ADD COLUMN no_compress_until INTEGER DEFAULT 0;
ALTER TABLE memory ADD COLUMN deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE memory ADD COLUMN deleted_at INTEGER;
ALTER TABLE memory ADD COLUMN cold_storage_ref TEXT;
ALTER TABLE memory ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE memory ADD COLUMN original_content_hash TEXT;
ALTER TABLE memory ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE memory ADD COLUMN last_accessed INTEGER;

-- Create indexes for compression queries
-- Composite index for worker queries (Fix #2)
CREATE INDEX IF NOT EXISTS idx_memory_compress_workflow 
    ON memory(compressed, no_compress, deleted, last_updated);
CREATE INDEX IF NOT EXISTS idx_memory_compress 
    ON memory(compressed, deleted, last_updated);
CREATE INDEX IF NOT EXISTS idx_memory_version 
    ON memory(version);
CREATE INDEX IF NOT EXISTS idx_memory_deleted 
    ON memory(deleted, deleted_at);
CREATE INDEX IF NOT EXISTS idx_memory_no_compress 
    ON memory(no_compress) WHERE no_compress = TRUE;
CREATE INDEX IF NOT EXISTS idx_memory_last_updated 
    ON memory(last_updated);

-- ============================================================================
-- Extended tool_cache table with compression fields
-- ============================================================================

ALTER TABLE tool_cache ADD COLUMN compressed BOOLEAN DEFAULT FALSE;
ALTER TABLE tool_cache ADD COLUMN compression_type TEXT;
ALTER TABLE tool_cache ADD COLUMN compression_metadata JSON;
ALTER TABLE tool_cache ADD COLUMN original_blob_id INTEGER REFERENCES original_blobs(id);
ALTER TABLE tool_cache ADD COLUMN original_length INTEGER;
ALTER TABLE tool_cache ADD COLUMN compressed_length INTEGER;
ALTER TABLE tool_cache ADD COLUMN semantic_similarity REAL DEFAULT 0.0;
ALTER TABLE tool_cache ADD COLUMN last_compressed_at INTEGER;
ALTER TABLE tool_cache ADD COLUMN compression_attempt_count INTEGER DEFAULT 0;
ALTER TABLE tool_cache ADD COLUMN no_compress BOOLEAN DEFAULT FALSE;
-- Issue #7: TTL-based no-compress re-evaluation
ALTER TABLE tool_cache ADD COLUMN no_compress_until INTEGER DEFAULT 0;
ALTER TABLE tool_cache ADD COLUMN deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE tool_cache ADD COLUMN deleted_at INTEGER;
ALTER TABLE tool_cache ADD COLUMN cold_storage_ref TEXT;
ALTER TABLE tool_cache ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE tool_cache ADD COLUMN original_content_hash TEXT;

-- Create indexes for tool_cache compression queries
CREATE INDEX IF NOT EXISTS idx_tool_cache_compress_workflow 
    ON tool_cache(compressed, no_compress, deleted, last_updated);
CREATE INDEX IF NOT EXISTS idx_tool_cache_compress 
    ON tool_cache(compressed, deleted, last_updated);
CREATE INDEX IF NOT EXISTS idx_tool_cache_version 
    ON tool_cache(version);
CREATE INDEX IF NOT EXISTS idx_tool_cache_last_updated 
    ON tool_cache(last_updated);

-- ============================================================================
-- Original blobs table for fallback decompression
-- With deduplication support (Phase 4E: Issue #14)
-- ============================================================================

CREATE TABLE IF NOT EXISTS original_blobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    item_type TEXT NOT NULL,
    compressed_at INTEGER,
    deleted_at INTEGER,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    reference_count INTEGER DEFAULT 1,
    -- UNIQUE constraint for deduplication: same item can have multiple blobs
    -- if content_hash is different, but we track reference_count
    UNIQUE(item_id, content_hash)
);

-- Primary dedup index: item_id + content_hash
CREATE UNIQUE INDEX IF NOT EXISTS idx_blobs_dedup 
    ON original_blobs(item_id, content_hash);

-- Index for blob cleanup (reference_count <= 1)
CREATE INDEX IF NOT EXISTS idx_blobs_refcount 
    ON original_blobs(reference_count) WHERE reference_count <= 1;

CREATE INDEX IF NOT EXISTS idx_blobs_item_id ON original_blobs(item_id);
CREATE INDEX IF NOT EXISTS idx_blobs_hash ON original_blobs(content_hash);
CREATE INDEX IF NOT EXISTS idx_blobs_deleted ON original_blobs(deleted_at);
CREATE INDEX IF NOT EXISTS idx_blobs_type ON original_blobs(item_type);

-- ============================================================================
-- Compression statistics table (optional, for historical tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS compression_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    strategy TEXT NOT NULL,
    original_length INTEGER NOT NULL,
    compressed_length INTEGER NOT NULL,
    compression_ratio REAL,
    semantic_similarity REAL,
    compressed_at INTEGER NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_compression_stats_item 
    ON compression_stats(item_id, item_type);
CREATE INDEX IF NOT EXISTS idx_compression_stats_date 
    ON compression_stats(compressed_at);

-- ============================================================================
-- Strategy Migration Tracking (Phase 4E: Issue #20)
-- ============================================================================

CREATE TABLE IF NOT EXISTS compression_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    old_strategy TEXT,
    new_strategy TEXT NOT NULL,
    old_version TEXT,
    new_version TEXT NOT NULL,
    old_content_hash TEXT,
    new_content_hash TEXT,
    migrated_at INTEGER DEFAULT (strftime('%s', 'now')),
    status TEXT DEFAULT 'pending',  -- pending, completed, failed
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_migrations_item 
    ON compression_migrations(item_id, item_type);
CREATE INDEX IF NOT EXISTS idx_migrations_status 
    ON compression_migrations(status) WHERE status != 'completed';
CREATE INDEX IF NOT EXISTS idx_migrations_date 
    ON compression_migrations(migrated_at);

-- ============================================================================
-- Integrity Scan Results (Phase 4E: Issue #17)
-- ============================================================================

CREATE TABLE IF NOT EXISTS integrity_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    scanned_at INTEGER DEFAULT (strftime('%s', 'now')),
    is_valid BOOLEAN,
    issues JSON,
    was_repaired BOOLEAN DEFAULT FALSE,
    repaired_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_integrity_job 
    ON integrity_scan_results(job_id);
CREATE INDEX IF NOT EXISTS idx_integrity_item 
    ON integrity_scan_results(item_id, item_type);
CREATE INDEX IF NOT EXISTS idx_integrity_valid 
    ON integrity_scan_results(is_valid) WHERE is_valid = FALSE;

-- ============================================================================
-- Migration functions
-- ============================================================================

-- NOTE: Removed problematic auto-update triggers (memory_on_write, tool_cache_on_write)
-- Version and last_updated should be updated explicitly in application code
-- to avoid recursion and ensure deterministic behavior.

-- Function to update last_accessed on retrieval (safe - AFTER trigger)
CREATE TRIGGER IF NOT EXISTS memory_on_access 
    AFTER UPDATE ON memory
    WHEN NEW.last_accessed IS NULL OR OLD.last_accessed != NEW.last_accessed
BEGIN
    UPDATE memory SET last_accessed = strftime('%s', 'now') WHERE id = NEW.id;
END;

-- Function to auto-generate content hash (safe - BEFORE INSERT)
CREATE TRIGGER IF NOT EXISTS memory_content_hash
    BEFORE INSERT ON memory
    WHEN NEW.original_content_hash IS NULL
BEGIN
    SELECT NEW.original_content_hash = 
        lower(hex(sha256(NEW.content)));
END;

-- ============================================================================
-- Views for monitoring
-- ============================================================================

-- Compression status view
CREATE VIEW IF NOT EXISTS v_compression_status AS
SELECT 
    'memory' as item_type,
    COUNT(*) as total_items,
    SUM(CASE WHEN compressed THEN 1 ELSE 0 END) as compressed_items,
    SUM(CASE WHEN deleted THEN 1 ELSE 0 END) as deleted_items,
    SUM(CASE WHEN no_compress THEN 1 ELSE 0 END) as no_compress_items,
    AVG(CASE WHEN compressed THEN semantic_similarity END) as avg_similarity,
    AVG(CASE WHEN compressed THEN 
        CAST(original_length AS REAL) / NULLIF(compressed_length, 0) 
    END) as avg_ratio
FROM memory
UNION ALL
SELECT 
    'tool_cache' as item_type,
    COUNT(*) as total_items,
    SUM(CASE WHEN compressed THEN 1 ELSE 0 END) as compressed_items,
    SUM(CASE WHEN deleted THEN 1 ELSE 0 END) as deleted_items,
    SUM(CASE WHEN no_compress THEN 1 ELSE 0 END) as no_compress_items,
    AVG(CASE WHEN compressed THEN semantic_similarity END) as avg_similarity,
    AVG(CASE WHEN compressed THEN 
        CAST(original_length AS REAL) / NULLIF(compressed_length, 0) 
    END) as avg_ratio
FROM tool_cache;

-- Items ready for compression with priority scoring (Phase 4E: Issue #16)
-- Priority = f(normalized_savings, normalized_coldness, normalized_size)
-- Each factor is normalized to 0-1 range before applying weights
CREATE VIEW IF NOT EXISTS v_compression_candidates AS
SELECT 
    id,
    'memory' as item_type,
    session_id,
    LENGTH(content) as content_length,
    last_updated,
    version,
    -- Estimated savings (assuming 30% compression)
    CAST(LENGTH(content) * 0.3 AS INTEGER) as estimated_savings,
    -- Coldness score (days since access)
    (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 as coldness_days,
    -- Composite priority score (normalized)
    (
        -- savings_score: cap at 30KB equivalent (100KB content)
        0.4 * MIN(CAST(LENGTH(content) * 0.3 AS REAL) / 30720.0, 1.0) +
        -- coldness_score: cap at 90 days
        0.3 * MIN((strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 / 90.0, 1.0) +
        -- size_score: cap at 1MB
        0.3 * MIN(CAST(LENGTH(content) AS REAL) / 1048576.0, 1.0)
    ) as priority_score
FROM memory
WHERE compressed = FALSE
  AND no_compress = FALSE
  AND deleted = FALSE
  AND last_updated < (strftime('%s', 'now') - 604800)  -- 7 days
UNION ALL
SELECT 
    id,
    'tool_cache' as item_type,
    tool_name as session_id,
    LENGTH(content) as content_length,
    last_updated,
    version,
    -- Estimated savings (assuming 30% compression)
    CAST(LENGTH(content) * 0.3 AS INTEGER) as estimated_savings,
    -- Coldness score (days since access)
    (strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 as coldness_days,
    -- Composite priority score (normalized)
    (
        -- savings_score: cap at 30KB equivalent
        0.4 * MIN(CAST(LENGTH(content) * 0.3 AS REAL) / 30720.0, 1.0) +
        -- coldness_score: cap at 90 days
        0.3 * MIN((strftime('%s', 'now') - COALESCE(last_accessed, last_updated)) / 86400.0 / 90.0, 1.0) +
        -- size_score: cap at 1MB
        0.3 * MIN(CAST(LENGTH(content) AS REAL) / 1048576.0, 1.0)
    ) as priority_score
FROM tool_cache
WHERE compressed = FALSE
  AND no_compress = FALSE
  AND deleted = FALSE
  AND last_updated < (strftime('%s', 'now') - 604800);  -- 7 days

-- Items ready for soft delete with SAFE logic (Phase 4E: Issue #11)
-- FIXED: Uses AND instead of OR to prevent deleting new items with low access
CREATE VIEW IF NOT EXISTS v_soft_delete_candidates AS
SELECT 
    id,
    'memory' as item_type,
    LENGTH(content) as content_length,
    last_accessed,
    access_count,
    (strftime('%s', 'now') - last_accessed) / 86400.0 as days_since_access
FROM memory
WHERE compressed = TRUE
  AND deleted = FALSE
  -- SAFER: Only delete items that are BOTH old AND rarely accessed
  AND last_accessed < (strftime('%s', 'now') - 2592000)  -- 30 days old
  AND access_count < 3  -- AND rarely accessed
UNION ALL
SELECT 
    id,
    'tool_cache' as item_type,
    LENGTH(content) as content_length,
    last_accessed,
    access_count,
    (strftime('%s', 'now') - last_accessed) / 86400.0 as days_since_access
FROM tool_cache
WHERE compressed = TRUE
  AND deleted = FALSE
  -- SAFER: Only delete items that are BOTH old AND rarely accessed  
  AND last_accessed < (strftime('%s', 'now') - 2592000)  -- 30 days old
  AND access_count < 3;  -- AND rarely accessed
