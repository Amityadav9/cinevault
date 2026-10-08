-- =====================================================================================
-- 01 · EXPLAIN & indexes: see *why* a query is fast or slow
-- =====================================================================================
-- Two ways to see a plan in pgAdmin's Query Tool:
--
--   1) TEXT plan: highlight a whole "EXPLAIN (ANALYZE, BUFFERS) SELECT …;" or a BEGIN…ROLLBACK
--      block → F5. The plan appears as rows in "Data Output".
--
--   2) DIAGRAM: highlight ONLY the bare "SELECT …;" (no EXPLAIN word, no SET/BEGIN) → toolbar
--      Explain (E button, F7 = estimate) or Explain Analyze (bar-chart button, Shift+F7 = real run).
--      An "Explain" tab appears at the bottom → Graphical / Analysis / Statistics.
--      pgAdmin adds "EXPLAIN (…)" itself, so highlighting EXPLAIN or SET gives a syntax error.
--      To compare without an index: F5 "SET enable_bitmapscan = off;" → Explain Analyze the
--      SELECT → F5 "RESET enable_bitmapscan;"
--
-- Reading a plan, bottom-up (innermost node runs first):
--   Seq Scan              read every row of the table
--   Index Scan            walk the index, fetch matching rows one by one
--   Bitmap Index Scan     index → bitmap of matching pages → Bitmap Heap Scan reads those pages
--   Nested Loop / Hash Join / Merge Join   the three ways to join two inputs
--   "Rows Removed by Filter"   work that an index could have avoided
--
-- Measured on this DB (750k movies, 345k ratings):
--   A  popular movies, sorted     8.4 ms → 3.1 ms with index   (small table: modest gain)
--   B  fuzzy title % '...'         331 ms →  25 ms  trigram index (~13x)
--   C  title ILIKE '%godfather%'    59 ms → 5.8 ms  trigram index (~10x)
-- =====================================================================================


-- -------------------------------------------------------------------------------------
-- A. B-tree index on ratings.num_votes
-- -------------------------------------------------------------------------------------
-- Postgres DDL is *transactional*: we create the index inside BEGIN … ROLLBACK, measure it,
-- and roll it back, so nothing changes. (Most other databases can't do this.)
-- The permanent version of this index is added by migration 0002.

BEGIN;

-- A1: no index yet → expect "Parallel Seq Scan on ratings" + "Rows Removed by Filter: ~170k"
EXPLAIN (ANALYZE, BUFFERS)
SELECT m.title, r.avg_rating, r.num_votes
FROM ratings r
JOIN movies m USING (tconst)
WHERE r.num_votes >= 100000
ORDER BY r.avg_rating DESC
LIMIT 20;

CREATE INDEX tmp_ratings_num_votes ON ratings (num_votes);
ANALYZE ratings;   -- refresh statistics so the planner knows about the new index

-- A2: same query → expect "Bitmap Index Scan on tmp_ratings_num_votes", no rows removed
EXPLAIN (ANALYZE, BUFFERS)
SELECT m.title, r.avg_rating, r.num_votes
FROM ratings r
JOIN movies m USING (tconst)
WHERE r.num_votes >= 100000
ORDER BY r.avg_rating DESC
LIMIT 20;

-- A3: selectivity matters! Ask for almost everything → the planner IGNORES the index,
-- because reading the whole table sequentially is cheaper than 300k index lookups.
EXPLAIN
SELECT count(*) FROM ratings WHERE num_votes >= 5;

ROLLBACK;   -- index gone again; check: \d ratings  (or pgAdmin → ratings → Indexes)


-- -------------------------------------------------------------------------------------
-- B. Trigram (pg_trgm) GIN index on movies.title: fuzzy search
-- -------------------------------------------------------------------------------------

-- B1: with the index → "Bitmap Index Scan on ix_movies_title_trgm"
-- Note "Rows Removed by Index Recheck": the index returns *candidates* sharing trigrams,
-- then Postgres re-checks the real similarity on each one (a "lossy" index).
EXPLAIN (ANALYZE, BUFFERS)
SELECT title FROM movies WHERE title % 'intersteller';

-- B2: pretend the index doesn't exist (SET LOCAL lasts only until ROLLBACK)
BEGIN;
SET LOCAL enable_bitmapscan = off;
SET LOCAL enable_indexscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT title FROM movies WHERE title % 'intersteller';   -- Parallel Seq Scan, ~13x slower
ROLLBACK;

-- B3: the similarity threshold behind %  (default 0.3). Lower = more (worse) matches.
SHOW pg_trgm.similarity_threshold;
SELECT title, similarity(title, 'intersteller') FROM movies WHERE title % 'intersteller'
ORDER BY 2 DESC LIMIT 10;


-- -------------------------------------------------------------------------------------
-- C. Bonus: the same trigram index accelerates ILIKE '%...%'
-- -------------------------------------------------------------------------------------
-- A normal B-tree index can only help with a *prefix* ('godfather%'), never a leading
-- wildcard ('%godfather%'). The trigram index can.

EXPLAIN ANALYZE SELECT title, year FROM movies WHERE title ILIKE '%godfather%';

BEGIN;
SET LOCAL enable_bitmapscan = off;
SET LOCAL enable_indexscan = off;
EXPLAIN ANALYZE SELECT title, year FROM movies WHERE title ILIKE '%godfather%';
ROLLBACK;


-- -------------------------------------------------------------------------------------
-- D. Look around: which indexes exist, how big are they, are they used?
-- -------------------------------------------------------------------------------------

SELECT tablename, indexname, indexdef
FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;

SELECT relname AS table_name,
       pg_size_pretty(pg_table_size(relid))   AS table_size,
       pg_size_pretty(pg_indexes_size(relid)) AS indexes_size
FROM pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;

-- idx_scan = how often each index was used since stats were reset
SELECT relname AS table_name, indexrelname AS index_name, idx_scan
FROM pg_stat_user_indexes ORDER BY idx_scan DESC;
