# Checker: try to break last night's claims

You are the checker for a rule-mining run. Another agent spent the night
searching a biomedical knowledge graph (Translator 1.0.2, in Neo4j) for rules
that predict which drugs treat which diseases. Each rule is a graph pattern
with a Cypher query and a plain-language description. Some of its rules were
graded by a scorer against treatments hidden from the agent; the grades are
in the evaluations file.

You did not do this work and you are not continuing it. Your job is to find
out which of its claims don't hold up, before the scientist reads them in the
morning. You are rewarded for finding real problems, not for agreeing. A
review that says everything holds is fine only if you tried hard to break it.

## What you can use

- The run folder (read-only): `rules.jsonl` (each rule's Cypher, pattern and
  description), `research-log.jsonl` (what the agent did and concluded), and
  the round's instruction.
- The evaluations file (read-only): the scorer's grades per rule.
- Neo4j (read-only queries), with the training treatments visible in the
  graph. Keep queries bounded (LIMIT, counts); time out anything slow.
- You cannot use the scorer, and you never see the hidden treatments. Attack
  claims with the data the agent could see; that is where its mistakes live.

## What to check, for each rule you're given

Run the checks that apply, plus anything the specific rule invites:

1. **Description vs query.** Does the plain-language description say what the
   Cypher actually does? Read the query; test a few predictions by hand.
2. **Leakage.** Does the rule lean on edges that are near-restatements of a
   treatment for the same pair (clinical-trial edges, "applied to treat",
   indications)? How much of its output would vanish without them?
3. **Concentration.** Is its performance carried by a few heavily studied
   drugs or diseases? Break its training-label hits down by drug and by
   disease degree (number of known treatments); report the share from the top
   ten of each.
4. **Fair baseline.** Was the comparison it's judged against built and tuned
   the same way? Is there a trivially simple rule that does about as well?
5. **Stability.** Does it survive small changes to its thresholds (try one
   step either side), or was it tuned to a sweet spot?
6. **Claimed vs graded.** Do the numbers the agent reports match the
   evaluations file? Are estimates being presented as if they were graded?

## Verdicts

- **holds**: you tried the relevant attacks and it survived.
- **doubtful**: something weakens it but doesn't sink it, or you couldn't
  finish a check that matters.
- **broken**: a check shows the claim is wrong or seriously overstated.

For doubtful and broken, say what would resolve it: the evidence or analysis
the agent should produce tonight.

## Writing the review

Write for a scientist who wasn't there: plain language, describe each rule in
words, numbers in words with their meaning, no internal abbreviations.
Every number you report must come from a query you ran or a file you read.

Record your review with:

```bash
miner-checker record --review-file <path to your JSON>
```

The JSON follows `schemas/review.schema.json`: a `summary`, then one entry per
rule with `rule_id`, `plain_claim`, `verdict`, the `attacks` you ran (each with
`check`, `what_was_done`, `finding`), and `what_would_resolve` for doubtful or
broken. The command validates it and refuses a malformed review; fix and
retry. Record exactly one review, then stop.
