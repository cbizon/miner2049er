# Treats Rule-Mining Notes

## Evaluation

The target is semantic `biolink:treats`, including present descendants
`biolink:ameliorates_condition` and
`biolink:preventative_for_condition`. Neo4j queries expand this closure
explicitly.

- Training: 25,161 target pairs.
- Validation: 2,351 pairs exclusive to `infores:drug-repurposing-hub`.
- Blind: 1,476 pairs exclusive to `infores:ttd`; not inspected or scored.
- Precision is a lower bound because unlabeled chemical-disease pairs are not
  known negatives.

## Retained Rules

### TREAT-I03-R019

Treatment-free, medium mechanism. A drug directly binds and decreases a causal
gene, the chemical has at most 50 qualified decreased-gene targets, the causal
gene is linked to at most 12 diseases, the MONDO disease is not an ontology
hub, and no direct adverse relation connects the pair.

- 244 candidate pairs.
- 26 visible target hits.
- 10.66% visible precision lower bound.
- 3 validation hits.
- 1.36% validation precision lower bound.

This is the current treatment-free precision/coverage compromise. Its main
limitation is missing gain-of-function versus loss-of-function disease
direction.

### TREAT-I04-R026

Treatment-evidence, medium mechanism. R019 plus an independently sourced
`infores:multiomics-clinicaltrials` assertion for the same drug-disease pair.

- 37 candidate pairs.
- 21 visible target hits.
- 56.76% visible precision lower bound.
- 3 validation hits.
- 15.79% validation precision lower bound.

This is the current precision-skewed predictive rule. It remains
treatment-oriented rather than a purely mechanistic discovery rule.

### TREAT-I05-R031

Treatment-free, medium mechanism. R019's low-fanout branch is retained, but a
high-fanout causal gene is rescued when its causal literature has NPMI at least
0.5, it ranks among the disease's top three genes, it has at least five causal
publications, and it has either a non-SemMed source or at least four direct
gene-disease relation types.

- 250 candidate pairs.
- 27 visible target hits.
- 10.80% visible precision lower bound.
- 3 validation hits.
- 1.33% validation precision lower bound.

Compared with R019, this adds six high-fanout candidates and one known target
while slightly improving visible precision and recall. It is the retained
treatment-free extension for common diseases.

### TREAT-I05-R030

Treatment-evidence, medium mechanism. R026 is extended with the looser
disease-relative rescue and the same independently sourced
`infores:multiomics-clinicaltrials` requirement.

- 43 candidate pairs.
- 22 visible target hits.
- 51.16% visible precision lower bound.
- 3 validation hits.
- 12.50% validation precision lower bound.

Compared with R026, this adds six candidates and one known target. It is
retained as the broader-coverage clinical Pareto choice; R026 remains the
higher-precision choice.

## Disease-Relative Gene Relevance

The original R019 constraint is on global causal-gene fanout, not on the
number of genes associated with a disease. It favors genes that cause few
diseases. That works well for specificity but excludes central genes that may
still be highly relevant to a common disease.

`MINER_GENE_DISEASE_EVIDENCE` derives graph-internal pair features:

- causal-publication count for the gene-disease pair;
- publication NPMI normalized by the gene and disease publication marginals;
- rank of the gene within the disease by combined evidence;
- number of direct gene-disease relation types;
- primary-source and non-SemMed primary-source counts;
- compact disease-process support;
- gene causal-disease fanout and disease causal-gene count.

Raw publication and pathway counts were not adequate on their own. They reward
popular hubs: for example, TNF-asthma had 11 causal publications and extensive
graph support but only 0.119 publication NPMI. Disease-relative NPMI was more
discriminating because it asks whether the pair receives a disproportionate
share of the gene's and disease's literature.

The strict R031 incremental cohort contains one known target,
faricimab-diabetic retinopathy through VEGFA, and five unlabeled predictions:

- faricimab-ovarian hyperstimulation syndrome through VEGFA;
- pegaptanib-diabetic retinopathy through VEGFA;
- pegaptanib-ovarian hyperstimulation syndrome through VEGFA;
- luspatercept-pulmonary fibrosis through TGFB1;
- luspatercept-renal fibrosis through TGFB1.

These remain predictions, not validated negatives or positives. The rule is
still only medium-mechanism because literature concentration cannot establish
whether decreasing the target corrects or reproduces the disease mechanism.

TREAT-I05-R028 is superseded by the stricter R031. TREAT-I05-R029 isolates the
looser high-fanout rescue cohort for diagnosis; it found one visible target
among 12 candidates and no validation hits, so it is not retained.

## Diagnostic Result

TREAT-I04-R025 reached 75% visible precision over four candidates, but its only
novel prediction was indapamide for long QT syndrome. The path treats
inhibition of causal KCNH2 as corrective even though reduced KCNH2 activity can
produce long QT. The rule is retained as `diagnostic_failure`, not as a winner.

This failure establishes a hard requirement for future high-mechanism rules:
the graph must encode or derive whether the disease is driven by increased or
decreased target activity. Additional path length and corroboration do not
repair missing causal direction.

## Iteration 6: Nonlinear Context

Iteration 6 tested anatomy, phenotype localization, disease-process context,
shared causal-gene modules, physical interactions, signed regulation, and
causal-target indication transfer. All rules remain `medium` mechanism because
the graph still does not encode whether increased or decreased activity of a
causal disease gene produces the disease.

### TREAT-I06-R037

Treatment-free. R031 plus a Bgee human-gene expression / disease-anatomy cycle
and exclusion of an exact shared drug-side-effect / disease-phenotype node.

- 74 candidate pairs.
- 17 visible target hits.
- 22.97% visible precision lower bound.
- 1 DRH validation hit.
- 1.72% validation precision lower bound.

The shared adverse-phenotype exclusion removes five unresolved candidates and
retains every visible hit from R032. R037 is the broad tissue-context point on
the treatment-free front.

### TREAT-I06-R052 and R054

Treatment-free. These rules require the same anatomy to have disease-location
degree at most 50 and Bgee human-gene expression degree at most 6,000 or 8,000.

| Rule | Candidates | Visible hits | Visible precision LB | DRH hits | Validation precision LB |
| --- | ---: | ---: | ---: | ---: | ---: |
| R052, degree <=6,000 | 24 | 7 | 29.17% | 1 | 5.56% |
| R054, degree <=8,000 | 32 | 8 | 25.00% | 1 | 4.00% |

R052 is the higher-precision point and R054 the higher-coverage point. The
intermediate 7,000 threshold is dominated. Eslicarbazepine-epilepsy is the DRH
validation hit. The unresolved R052 cohort is concentrated in ERBB2/EGFR
breast-neoplasm predictions, with generic poisoning as a clear residual
failure mode.

### TREAT-I06-R049

Treatment-free. R037 plus a disease phenotype that localizes to the same
anatomy in which Bgee expresses the inhibited causal gene.

- 11 candidate pairs.
- 4 visible target hits.
- 36.36% visible precision lower bound.
- 0 DRH validation hits.
- 7 unresolved predictions.

This is a small visible-precision point with nonzero discovery capacity. It is
retained, but the absence of a validation hit makes its estimate less robust
than R052.

### TREAT-I06-R048

Uses a non-blind treatment edge. A drug treats an anchor disease, inhibits the
same causal gene for anchor and candidate, and anchor and candidate are within
three directed MONDO subclass steps.

- 9 candidate pairs.
- 3 visible target hits.
- 33.33% visible precision lower bound.
- 0 DRH validation hits.
- 6 unresolved predictions.

The ontology constraint removes unrelated transfers such as
ALS-to-poisoning while retaining disease-family transfers. It is retained as
the best mechanistic indication-transfer rule, but it is not treatment-free.

## Iteration 7: Translational-Anatomy Pareto Ladder

Iteration 7 searched the gap between the high-precision applied-treatment
rules and the broader independent-clinical rules. The successful signal was a
graded evidence ladder combining:

- direct binding and decreased target activity;
- a causal target-disease edge;
- `APPLIED_TO_TREAT` and/or independently sourced
  `IN_CLINICAL_TRIALS_FOR`;
- at least three Bgee expression / disease-anatomy overlaps where anatomy is
  used;
- a ceiling on the number of genes whose activity the drug decreases.

Five new rules are nondominated on the global visible precision-recall front:

| Rule | Evidence ladder | Candidates | Visible hits | Visible precision LB | DRH hits | Validation precision LB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| R059 | applied AND clinical | 14 | 13 | 92.86% | 1 | 50.00% |
| R060 | applied AND (clinical OR anatomy), target degree <=32 | 18 | 16 | 88.89% | 1 | 33.33% |
| R061 | R060 with target degree <=44 | 20 | 17 | 85.00% | 1 | 25.00% |
| R062 | anatomy AND (applied OR clinical), target degree <=30 | 28 | 19 | 67.86% | 3 | 25.00% |
| R063 | R062 with target degree <=45 | 31 | 20 | 64.52% | 3 | 21.43% |

R059 and R062 are also new points on the validation precision-recall front.
All five retain at least one non-blind unlabeled prediction. The nested visible
front continues through R026 at 21 visible hits and 56.76% precision.

The sole non-blind unlabeled R059 pair is
faricimab-choroidal neovascularization. The broader rules add coherent
graph-internal candidates including faricimab-blindness,
dronedarone-arrhythmia, diflunisal-amyloidosis, pegaptanib-diabetic
retinopathy, tucatinib and margetuximab-breast cancer, and
pexidartinib-Plexosarcoma. Romiplostim-Plexosarcoma through KIT is the clearest
residual questionable prediction.

The three R062 DRH validation hits are eslicarbazepine-epilepsy,
lumacaftor-cystic fibrosis, and tezacaftor-cystic fibrosis. These rules remain
medium mechanism because the translational assertions are treatment-oriented
and the disease-causing direction of target activity is still unavailable.

## Pathway and Interaction Findings

The original `MINER_DISEASE_PROCESS_SUPPORT` feature is narrow: it starts from
`GENE_ASSOCIATED_WITH_CONDITION`, which covers only 79 disease nodes in this
build. Iteration 6 added graph-native process context:

- disease/process `GENETIC_ASSOCIATION` degree;
- phenotype/process `GENETIC_ASSOCIATION` degree;
- causal gene overlap with directly disease-associated processes;
- causal gene overlap with phenotype-associated processes;
- processes shared with a second causal disease gene.

Among 2,389 causal gene-disease evidence pairs, 127 share a directly
disease-associated process, only 3 share a phenotype-mediated process, and
1,101 share a process with another causal gene.

Shared-process rules R038-R040 retained the DRH hit but lowered visible
precision to 18.5-20.0%. Compact GOA process membership and repeated causal
neighbors are therefore corroborative, not selective, in this graph.

Unsigned SIGNOR physical-neighbor expansion R041 found two validation hits but
only 21 visible hits among 438 candidates. Compact-pathway filtering reduced
coverage without restoring precision. Signed target-to-driver rules likewise
failed the label test: the anatomy-specific signed families R055-R058 produced
19-76 candidates and no visible targets. These remain diagnostic prediction
cohorts, not predictive rules.

The coherent signed validation path found before anatomy tightening was
larotrectinib -> ABL1 -> JAK2 -> myeloproliferative neoplasm, with ABL1 and
JAK2 sharing compact processes and blood/marrow anatomy. This confirms that
the motif can be biologically meaningful, but it is not label-predictive as a
general rule in the current graph.

## Missing Information

The failed and successful rules identify concrete graph gaps:

- Disease `CAUSES` edges lack gain-of-function / loss-of-function or increased
  / decreased activity direction. This is the main barrier to `high` mechanism
  scores.
- Disease and phenotype anatomy assertions are entirely SemMedDB-derived in
  this build. Bgee provides independent expression evidence, but broad
  literature anatomy still creates false joins.
- Disease `HAS_PHENOTYPE` nodes are HPO, while GeneticsKP gene-phenotype
  `GENE_ASSOCIATED_WITH_CONDITION` edges are predominantly EFO. Exact and
  HPO-near shared gene/disease phenotype rules consequently have zero coverage.
  An EFO-HPO bridge or normalized phenotype similarity is missing.
- Direct disease-process genetic associations cover relatively few causal
  gene-disease pairs, and phenotype-mediated process coverage is nearly absent.
- Treatment labels are incomplete. Several unresolved cohorts cluster around
  coherent drug/target/disease families, so precision remains a lower bound.

## Executable Queries

Every rule has complete Cypher in `rules/treats-rules.toml`. Selected retained
and diagnostic motifs also reference executable payloads under `rules/trapi/`.

```bash
uv run miner-run-rule-trapi --rule TREAT-I06-R052
uv run miner-run-rule-trapi --rule TREAT-I06-R049
uv run miner-run-rule-trapi --rule TREAT-I06-R048
uv run miner-run-rule-trapi --rule TREAT-I07-R059
uv run miner-run-rule-trapi --rule TREAT-I07-R060
uv run miner-run-rule-trapi --rule TREAT-I07-R062
```

Gandalf executes the positive motif and applies Biolink predicate inheritance.
Cypher remains authoritative for degree, rank, provenance, absence,
cardinality, and bounded-path constraints. The source-exclusive TTD partition
was not inspected or scored during iteration 6.

## Iteration 8: Multichannel Translational Frontier

Iteration 8 built a cached matrix of 1,998 direct inhibited-causal-target path
rows and searched 44,595 distinct conjunctions of up to four graph-internal
conditions. Signals included binding provenance consensus, multiomics clinical
trials, FAERS applied-use assertions, CTD and targeted-text treatment-family
assertions, disease-relative causal literature, relation diversity, and Bgee
anatomy context.

The search cache records only training-hit and DRH-validation-hit booleans.
Source-exclusive TTD target pairs and unlabeled pairs are deliberately
indistinguishable during search. Selected rules were then rerun from their
compiled Cypher through the authoritative evaluator.

Thirty distinct rules, R064-R093, are nondominated on the global visible
precision-recall surface. Every rule has at least one DRH validation hit and at
least one unresolved-or-blind prediction.

| Rule | Candidates | Visible hits | Visible precision LB | DRH hits | Unresolved/blind |
| --- | ---: | ---: | ---: | ---: | ---: |
| TREAT-I08-R064 | 21 | 20 | 95.24% | 1 | 1 |
| TREAT-I08-R065 | 31 | 29 | 93.55% | 1 | 2 |
| TREAT-I08-R066 | 36 | 33 | 91.67% | 1 | 3 |
| TREAT-I08-R067 | 39 | 34 | 87.18% | 1 | 5 |
| TREAT-I08-R068 | 55 | 46 | 83.64% | 1 | 9 |
| TREAT-I08-R069 | 61 | 50 | 81.97% | 1 | 11 |
| TREAT-I08-R070 | 65 | 52 | 80.00% | 1 | 13 |
| TREAT-I08-R071 | 71 | 56 | 78.87% | 1 | 15 |
| TREAT-I08-R072 | 75 | 58 | 77.33% | 1 | 17 |
| TREAT-I08-R073 | 79 | 60 | 75.95% | 1 | 19 |
| TREAT-I08-R074 | 83 | 63 | 75.90% | 1 | 20 |
| TREAT-I08-R075 | 88 | 66 | 75.00% | 1 | 22 |
| TREAT-I08-R076 | 92 | 68 | 73.91% | 1 | 24 |
| TREAT-I08-R077 | 99 | 73 | 73.74% | 1 | 26 |
| TREAT-I08-R078 | 108 | 78 | 72.22% | 1 | 30 |
| TREAT-I08-R079 | 124 | 81 | 65.32% | 1 | 43 |
| TREAT-I08-R080 | 138 | 89 | 64.49% | 1 | 49 |
| TREAT-I08-R081 | 144 | 92 | 63.89% | 1 | 52 |
| TREAT-I08-R082 | 159 | 100 | 62.89% | 1 | 59 |
| TREAT-I08-R083 | 161 | 101 | 62.73% | 1 | 60 |
| TREAT-I08-R084 | 164 | 102 | 62.20% | 1 | 62 |
| TREAT-I08-R085 | 186 | 111 | 59.68% | 5 | 75 |
| TREAT-I08-R086 | 203 | 116 | 57.14% | 5 | 87 |
| TREAT-I08-R087 | 211 | 120 | 56.87% | 5 | 91 |
| TREAT-I08-R088 | 215 | 121 | 56.28% | 5 | 94 |
| TREAT-I08-R089 | 226 | 122 | 53.98% | 5 | 104 |
| TREAT-I08-R090 | 291 | 127 | 43.64% | 6 | 164 |
| TREAT-I08-R091 | 296 | 128 | 43.24% | 6 | 168 |
| TREAT-I08-R092 | 306 | 131 | 42.81% | 5 | 175 |
| TREAT-I08-R093 | 316 | 132 | 41.77% | 5 | 184 |

The final global visible surface contains these 30 rules plus the broad
clinical-trial and applied-treatment benchmarks R011 and R013. The previous
R059-R063 ladder and all other older mechanistic rules are globally dominated
by the new points, although the treatment-free front is unchanged.

R064's sole unlabeled prediction is sorafenib-Plexosarcoma. R065 adds
ibrutinib-immunodeficiency disease and fedratinib-myeloproliferative neoplasm.
Broader cohorts include plausible oncology extensions but also clear warnings:
generic disease nodes, drug-specific fanout, and some contraindicated pairs.
The rules are therefore medium-mechanism translational classifiers, not thirty
independent mechanistic discoveries. Adverse-pair exclusion and disease
specificity are the next refinement targets.
