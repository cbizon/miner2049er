// Direct neighbors with full edge provenance.
MATCH (s:Entity {id: "NCBIGene:98558"})-[r]->(o)
RETURN s.id, type(r), r.predicate, o.id, o.name,
       r.primary_knowledge_sources, r.aggregator_knowledge_sources
LIMIT 25;

// Predicate and endpoint-category counts for candidate rule templates.
MATCH (s)-[r]->(o)
UNWIND s.categories AS subject_category
UNWIND o.categories AS object_category
RETURN subject_category,
       r.predicate AS predicate,
       object_category,
       count(*) AS edge_count
ORDER BY edge_count DESC
LIMIT 100;
