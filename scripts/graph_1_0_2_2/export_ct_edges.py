"""Export every clinical-trials KP edge of the loaded graph, with its trial ids, as JSONL.

Reads Neo4j over bolt (port-forward miner-neo4j-0 to localhost:17687 first; NEO4J_PW in the environment).
One line per edge: edge id, subject, predicate type, object, the KP's original subject and object, and the
supporting trials as [NCT id, tested-intervention flag].

    uv run python scripts/graph_1_0_2_2/export_ct_edges.py data/identity/ct-edges-all-1.0.2.1.jsonl
"""

import os
import sys

import orjson
from neo4j import GraphDatabase

QUERY = """MATCH (n)-[r]->(d) WHERE 'infores:multiomics-clinicaltrials' IN r.primary_knowledge_sources
RETURN r.edge_id AS id, n.id AS s, type(r) AS p, d.id AS o, r.original_subject AS os, r.original_object AS oo,
       r.supporting_studies_json AS st"""


def main() -> None:
    driver = GraphDatabase.driver("bolt://localhost:17687", auth=("neo4j", os.environ["NEO4J_PW"]))
    count = 0
    with driver.session() as session, open(sys.argv[1], "wb") as out:
        for record in session.run(QUERY):
            studies = orjson.loads(record["st"] or "{}")
            trials = [[key.split(":", 1)[1], value.get("clinical_trial_tested_intervention")]
                      for key, value in studies.items()]
            out.write(orjson.dumps({"id": record["id"], "s": record["s"], "p": record["p"], "o": record["o"],
                                    "os": record["os"], "oo": record["oo"], "trials": trials}) + b"\n")
            count += 1
    print(count)


if __name__ == "__main__":
    main()
