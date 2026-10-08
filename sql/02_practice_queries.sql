-- =====================================================================================
-- 02 · SQL practice on CineVault data
-- =====================================================================================
-- Each block: what it teaches → the query → a "try" exercise.
-- Tables: movies, ratings, genres, movie_genres, moods, mood_genres  (watchlist: empty yet)
-- =====================================================================================


-- -------------------------------------------------------------------------------------
-- 1. JOIN + GROUP BY: stats per genre
-- -------------------------------------------------------------------------------------
-- Teaches: many-to-many join through movie_genres; LEFT JOIN keeps unrated movies;
-- count(*) counts rows, count(col) counts non-NULLs; avg() ignores NULLs.

SELECT g.name                         AS genre,
       count(*)                       AS movies,
       count(r.tconst)                AS rated,
       round(avg(r.avg_rating), 2)    AS avg_rating
FROM genres g
JOIN movie_genres mg ON mg.genre_id = g.id
LEFT JOIN ratings r  ON r.tconst = mg.tconst
GROUP BY g.name
ORDER BY movies DESC;

-- Try: change LEFT JOIN → JOIN. Which column stops making sense, and why?
-- Try: add HAVING count(r.tconst) > 10000 to show only well-covered genres.


-- -------------------------------------------------------------------------------------
-- 2. WINDOW FUNCTION: top 3 per genre
-- -------------------------------------------------------------------------------------
-- Teaches: ROW_NUMBER() OVER (PARTITION BY …) ranks *within* each group without collapsing
-- rows like GROUP BY does. A CTE (WITH …) names the intermediate result for readability.

WITH ranked AS (
    SELECT g.name AS genre, m.title, m.year, r.avg_rating, r.num_votes,
           ROW_NUMBER() OVER (
               PARTITION BY g.id
               ORDER BY r.avg_rating DESC, r.num_votes DESC   -- tie-breaker: more votes
           ) AS rank_in_genre
    FROM movies m
    JOIN ratings r       USING (tconst)
    JOIN movie_genres mg USING (tconst)
    JOIN genres g        ON g.id = mg.genre_id
    WHERE r.num_votes >= 50000          -- ignore ratings from tiny audiences
)
SELECT genre, rank_in_genre, title, year, avg_rating
FROM ranked
WHERE rank_in_genre <= 3
ORDER BY genre, rank_in_genre;

-- Try: replace ROW_NUMBER with RANK and DENSE_RANK. When do the results differ? (hint: ties)


-- -------------------------------------------------------------------------------------
-- 3. YOUR MOODS: "Feel-good, rated 7.5+, under 2 hours"
-- -------------------------------------------------------------------------------------
-- Teaches: chaining 5 tables; GROUP BY a movie to count how many mood-genres it hits
-- (a movie that is Animation AND Comedy fits "Feel-good" better than one that's only Comedy);
-- string_agg to show which genres matched.

SELECT m.title, m.year, m.runtime_min, r.avg_rating,
       count(*)                   AS mood_genre_hits,
       string_agg(g.name, ', ')   AS matched_genres
FROM moods mo
JOIN mood_genres  mog ON mog.mood_id = mo.id
JOIN movie_genres mg  ON mg.genre_id = mog.genre_id
JOIN genres g         ON g.id = mg.genre_id
JOIN movies m         ON m.tconst = mg.tconst
JOIN ratings r        ON r.tconst = m.tconst
WHERE mo.name = 'Feel-good'
  AND r.avg_rating >= 7.5
  AND r.num_votes  >= 50000
  AND m.runtime_min <= 120
GROUP BY m.tconst, m.title, m.year, m.runtime_min, r.avg_rating
ORDER BY mood_genre_hits DESC, r.avg_rating DESC
LIMIT 20;

-- Try: other moods: 'Mind-bending', 'Spooky night', 'Edge of my seat'.
-- Try: edit a mood! e.g. add Fantasy to Feel-good, then re-run:
--   INSERT INTO mood_genres (mood_id, genre_id)
--   SELECT mo.id, g.id FROM moods mo, genres g WHERE mo.name = 'Feel-good' AND g.name = 'Fantasy';
-- Notice: 'Spooky night' top hits include "The Silence of the Lambs". Genre is a crude
-- proxy for mood. Phase 5 adds plot embeddings to do better.


-- -------------------------------------------------------------------------------------
-- 4. GROUP BY an expression: movies per decade
-- -------------------------------------------------------------------------------------
-- Teaches: integer division for bucketing; FILTER (WHERE …) for conditional counts;
-- percentile_cont = median (an "ordered-set aggregate").

SELECT (m.year / 10) * 10                                     AS decade,
       count(*)                                               AS movies,
       count(*) FILTER (WHERE r.num_votes >= 10000)           AS popular,
       round(avg(r.avg_rating), 2)                            AS avg_rating,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY m.runtime_min) AS median_runtime
FROM movies m
LEFT JOIN ratings r USING (tconst)
WHERE m.year BETWEEN 1920 AND 2029
GROUP BY 1
ORDER BY 1;

-- Try: why use the median rather than avg(runtime_min)? Run the data-quality block (#6) first.


-- -------------------------------------------------------------------------------------
-- 5. NOT EXISTS + a data-quality trap: "hidden gems"
-- -------------------------------------------------------------------------------------
-- Teaches: NOT EXISTS (anti-join) to exclude movies having a genre; spotting biased data.

SELECT m.title, m.year, r.avg_rating, r.num_votes
FROM movies m
JOIN ratings r USING (tconst)
WHERE r.avg_rating >= 8.0
  AND r.num_votes BETWEEN 5000 AND 30000
  AND NOT m.is_adult
  AND NOT EXISTS (
      SELECT 1 FROM movie_genres mg JOIN genres g ON g.id = mg.genre_id
      WHERE mg.tconst = m.tconst AND g.name = 'Documentary'
  )
ORDER BY r.avg_rating DESC, r.num_votes DESC
LIMIT 20;

-- Look at the years: the top is full of brand-new releases rated 9+ by early fans.
-- Try: add  AND m.year <= extract(year FROM now()) - 2  and compare. Much better gems!


-- -------------------------------------------------------------------------------------
-- 6. DATA QUALITY: always profile before you trust
-- -------------------------------------------------------------------------------------

-- Longest runtimes: "Logistics" (2012) is 51,420 min = 35 days. Real, but an outlier.
SELECT title, year, runtime_min, round(runtime_min / 60.0 / 24, 1) AS days
FROM movies ORDER BY runtime_min DESC NULLS LAST LIMIT 5;

-- Year range: includes announced future films
SELECT min(year), max(year), count(*) FILTER (WHERE year > extract(year FROM now())) AS future
FROM movies;

-- NULL coverage per column
SELECT count(*)                                   AS total,
       count(*) FILTER (WHERE year IS NULL)        AS no_year,
       count(*) FILTER (WHERE runtime_min IS NULL) AS no_runtime,
       count(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM movie_genres mg WHERE mg.tconst = movies.tconst)) AS no_genre
FROM movies;


-- -------------------------------------------------------------------------------------
-- 7. Challenge (write these yourself)
-- -------------------------------------------------------------------------------------
-- a) The 10 highest-rated movies of your birth year (min 10k votes).
-- b) Which genre PAIR occurs most often? (hint: self-join movie_genres on tconst
--    with mg1.genre_id < mg2.genre_id)
-- c) For each decade, the single best Sci-Fi movie (window function + filter).
-- d) Fuzzy + popularity: rank matches for 'the godfater' using
--    similarity(title, …) + 0.05 * log(num_votes + 1)   (this is the phase-2 matcher idea)
