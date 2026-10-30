# Self-hosted vector database and cosine indexing

## Deployment model

The vector database is embedded in the application process and persisted to a SQLite file at
`data/vectors.db` by default. There is no external service to provision. The database is created on
startup and the file can be backed up by copying it when the application is stopped, or by using the
SQLite backup API while it is running.

This is a real self-hosted deployment for a single-node application. It is not a distributed vector
service. The trade-off is deliberate: zero infrastructure, simple operations, and predictable
latency for small collections. For millions of vectors or multi-tenant traffic, use a dedicated
service such as pgvector, Qdrant, Milvus, Weaviate, or an ANN library such as FAISS.

Runtime properties:

- WAL journal mode allows one writer and multiple readers.
- Foreign keys are enabled so dropping a collection removes its vectors.
- Vectors and metadata are stored as JSON text.
- The unique key is `(collection_id, external_id)`, so upserts are idempotent.
- `PRAGMA synchronous = NORMAL` favors durability and throughput for a local tool.

## Schema

```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    metric TEXT NOT NULL DEFAULT 'cosine'
        CHECK (metric IN ('cosine', 'dot', 'euclidean')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vectors (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    vector TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (collection_id, external_id)
);
```

The B-tree indexes support collection scans and external identifier lookups. There is no vector
index in SQLite. Distance is computed in Python after reading the candidate rows.

## Cosine similarity

Cosine similarity measures the angle between two vectors and ignores magnitude:

```
cos(a, b) = sum(a_i * b_i) / (sqrt(sum(a_i^2)) * sqrt(sum(b_i^2)))
```

Properties used in this implementation:

- Identical direction returns 1.0.
- Orthogonal vectors return 0.0.
- Opposite direction returns -1.0.
- A zero vector has no direction, so the implementation defines similarity as 0.0.
- Dimensions must match.
- Values must be finite.
- The result is clamped to `[-1.0, 1.0]` to absorb floating point drift.

`math.fsum` is used for stable summation. No NumPy or other numerical library is used.

## Query path

1. Validate the query vector against the collection dimension.
2. Read stored rows in batches of 1,000 using `fetchmany` to keep memory bounded.
3. Optionally apply a metadata equality filter.
4. Compute cosine similarity for each candidate.
5. Keep the top k with a heap.
6. Sort the final results by descending score and ascending external identifier for deterministic
   output.

Complexity for one query is `O(N * D)` time for the distance computations plus `O(N log k)` for the
heap, where `N` is the number of vectors in the collection and `D` is the dimension. Loading the
rows from SQLite adds I/O proportional to the serialized size of the collection. There is no
sublinear index.

## Storage and write complexity

- Upsert is `O(D)` for validation and serialization plus a B-tree lookup and write.
- Delete is a B-tree lookup and delete.
- Creating an index on external identifiers is `O(N log N)` in the database.
- Backups are file copies. WAL checkpoints should be considered for consistent snapshots.
- The unique constraint gives idempotent writes, which matters when reprocessing receipts.

## Why brute force is acceptable here

A personal receipt history might contain thousands of receipts, not billions. At 10,000 receipts
with 256 dimensions, a query scans about 2.56 million floats. That is small for a local process. The
simplicity of brute force also makes recall exact: no approximate index means no missed neighbors.

The cost grows linearly. At millions of vectors, a full scan per query becomes slow. That is the
point to introduce an ANN index or a dedicated database.

## When to move to an ANN index

Consider HNSW, IVF, or product quantization when one or more of these is true:

- the collection no longer fits comfortably in memory
- p95 query latency exceeds the product target
- writes are frequent enough that index maintenance is cheaper than scans
- approximate recall is acceptable, with a recall target and an evaluation set

ANN introduces a new set of trade-offs: build time, memory, recall, and the need to tune parameters.
Measure recall against brute force before trusting it.

## Operational notes

- Use one database per environment and mount it on a persistent volume in Docker.
- Do not copy a live SQLite file while a writer is active without using a backup API or checkpoint.
- Monitor collection size, dimension mismatches, and query latency.
- Keep a dimension and embedder version in collection metadata or the collection name. Changing the
  embedding model requires a re-index, because vectors from different models are not comparable.
- Treat vector search as one signal. The receipt application combines it with exact SQL filters on
  dates, amounts, and item text. This hybrid approach is more reliable than vector search alone.

## Reproducing the vector checks

```bash
pytest tests/test_vector_similarity.py tests/test_vector_store.py
```

The tests cover zero vectors, mismatched dimensions, non-finite values, negative values, single
element vectors, tie ordering, persistence across connections, metadata filters, thresholds, and
cascade deletes.
