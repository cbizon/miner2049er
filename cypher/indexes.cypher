CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

CREATE INDEX entity_name IF NOT EXISTS
FOR (n:Entity) ON (n.name);

CREATE FULLTEXT INDEX entity_text IF NOT EXISTS
FOR (n:Entity) ON EACH [n.name, n.description, n.symbol];
