# Rule TRAPI Templates

These payloads are executable positive-motif queries for the local Gandalf
endpoint. They use pinned known examples so they can run safely as checked-in.
Replace the `subject` and `object` node `ids` to apply a motif to another pair.
The signed regulatory template pins its target and driver because the current
Gandalf planner rejects an edge whose endpoints are both unresolved.
It contains the signed molecular core only; shared-process and anatomy cycles
are applied by the complete Cypher rule.

Run a template by rule ID:

```bash
uv run miner-run-rule-trapi --rule TREAT-I06-R052
```

The complete rule remains the Cypher program in `../treats-rules.toml`.
Gandalf handles Biolink predicate inheritance and the positive query graph.
Cypher or post-processing applies degree, rank, provenance, cardinality, and
negative-existence constraints that are not expressible in the TRAPI query.

Iteration-7 rules reference the executable clinical or tissue branch templates.
Combined clinical/applied/anatomy query graphs trigger Gandalf's current
`Both nodes unpinned - bad query planning` failure even when every node is
pinned. The evidence conjunction or OR, minimum of three anatomical overlaps,
and degree thresholds therefore remain authoritative Cypher constraints.
