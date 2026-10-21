import math

from qdrant_client import QdrantClient, models


def validate_vector(vector, dimensions=768):
    if len(vector) != dimensions or not all(math.isfinite(float(v)) for v in vector) or not any(vector):
        raise ValueError('Invalid embedding output')
    return [float(v) for v in vector]


class VectorIndex:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=15)

    def initialize(self):
        if not self.client.collection_exists(self.settings.collection):
            self.client.create_collection(self.settings.collection,
                vectors_config=models.VectorParams(size=self.settings.dimensions, distance=models.Distance.COSINE))
        self.ready()
        for field in ('tags', 'dataset_id', 'embedding_identity'):
            self.client.create_payload_index(self.settings.collection, field, models.PayloadSchemaType.KEYWORD, wait=True)

    def ready(self):
        vector = self.client.get_collection(self.settings.collection).config.params.vectors
        if not isinstance(vector, models.VectorParams) or vector.size != self.settings.dimensions or vector.distance != models.Distance.COSINE:
            raise ValueError('Qdrant collection has an incompatible vector schema')

    def upsert(self, row, vector):
        self.client.upsert(self.settings.collection, wait=True, points=[models.PointStruct(
            id=str(row['index_id']), vector=validate_vector(vector, self.settings.dimensions),
            payload={key: row[key] for key in ('tags', 'dataset_id', 'embedding_identity')})])

    def search(self, vector, tags, limit, identity, offset=0):
        conditions = [models.FieldCondition(key='embedding_identity', match=models.MatchValue(value=identity))]
        if tags:
            conditions.append(models.FieldCondition(key='tags', match=models.MatchAny(any=tags)))
        return self.client.query_points(self.settings.collection, query=validate_vector(vector),
            query_filter=models.Filter(must=conditions), limit=limit, offset=offset,
            with_payload=False, with_vectors=False).points

    def point_ids(self, offset=None):
        points, next_offset = self.client.scroll(self.settings.collection,
            limit=100, offset=offset, with_payload=False, with_vectors=False)
        return [str(point.id) for point in points], next_offset

    def delete(self, ids):
        if ids:
            self.client.delete(self.settings.collection,
                points_selector=models.PointIdsList(points=[str(value) for value in ids]), wait=True)

    def close(self):
        self.client.close()
