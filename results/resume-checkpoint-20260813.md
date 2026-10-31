# Treats Rule-Mining Resume Checkpoint

Stopped at the user's explicit deadline instruction after safely reconciling
the final catalog change. This checkpoint is the authoritative restart state.

## Safe state

- No `miner-evaluate-rules`, `miner-inspect-rule`, ad hoc Cypher, or other
  campaign mining process is running.
- The local Gandalf server remains intentionally running on port 6429.
- TTD identities remain blind. No unresolved or TTD-only candidate identity
  was inspected.
- The append-only source of research history is
  `results/research-log-20260812-20260813.md`.
- Catalog: `rules/campaign-i09.toml`.
- Compiler: `src/miner2049er/rule_families.py`.
- Tests: `tests/test_rules.py`.
- Metrics library: `results/rule-library.json`.

## Final reconciliation

R493 was rerun only to refresh catalog metadata after R492 was rejected:
`results/runs/20260812T221418Z/summary.json`.

- Stored results: 488.
- Global visible Pareto: 32.
- Global validation Pareto: 9.
- Treatment-free visible Pareto: 16.
- Treatment-free validation Pareto: 10.
- R492: rejected, 2 pairs, 2 training, 0 novel.
- R493: rejected zero-pair direction control.

The strongest rules from the last completed mechanism block remain:

- R485: 9 pairs, 5 training, 4 novel, 55.56%, high mechanism.
- R486: 6 pairs, 4 training, 2 novel, 66.67%, high mechanism.
- R488: 17 pairs, 9 training, 8 novel, 52.94%, high mechanism.

All three are treatment-free visible Pareto entries.

## Resume point

Do not spend the next block tuning R485-R488 thresholds. Start a genuinely
different hypothesis family. The best queued option is a signed `AFFECTS`
gene-network bridge:

1. inventory bridge orientation, qualifiers, source, and target coverage around
   R472 or R488 pairs;
2. define corrective and worsening matched cells only where sign semantics are
   explicit;
3. evaluate partitions blind-safely;
4. inspect training and safe novel examples only;
5. append the hypothesis, executable Cypher, metrics, examples, ablations,
   failures, and graph limitations to the research log.

If that family is semantically unusable, move to a directional `PRODUCES`
mediator chain rather than another ontology threshold.

## Restart commands

```bash
pgrep -fl 'miner-evaluate-rules|miner-inspect-rule|python.*miner2049er'

.venv/bin/pytest -q tests/test_rules.py -k \
  'signed_regulatory_bridged_dual_arm or ontology_generalized_signed_interception or dual_process_ontology_convergence'

.venv/bin/ruff check src/miner2049er/rule_families.py tests/test_rules.py

.venv/bin/miner-evaluate-rules \
  --rules rules/campaign-i09.toml \
  --rule TREAT-I09-R493 \
  --neo4j-password translator-local \
  --timeout-seconds 120 \
  --output-dir results/runs
```

Neo4j access may require local-socket permission in a restricted execution
environment. The expected post-refresh surface counts are `32/9/16/10`.
