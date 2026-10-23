"""Explicit maintenance for the dedicated archive collection."""


def cleanup_vectors(repo, index, *, apply=False):
    counts = {'scanned': 0, 'orphaned': 0, 'deleted': 0}
    with repo.worker_lock() as worker:
        offset = None
        while True:
            worker.assert_worker()
            ids, offset = index.point_ids(offset)
            referenced = worker.referenced_index_ids(ids)
            orphaned = [value for value in ids if value not in referenced]
            counts['scanned'] += len(ids)
            counts['orphaned'] += len(orphaned)
            if apply and orphaned:
                worker.assert_worker()
                # Explicit IDs only. A successor always generates fresh attempt
                # IDs, so even a delayed delete cannot remove its new vectors.
                index.delete(orphaned)
                counts['deleted'] += len(orphaned)
            if offset is None:
                return counts
