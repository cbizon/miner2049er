# Drug and disease identity review log

Decisions on candidate node pairs for graph 1.0.2.1, made one group at a time.

For each group we record where it came from, how it is defined, and two decisions:

- **Babel:** does this go upstream as a Babel issue? If yes, we also fix it in our
  local derived graph.
- **miner2049er:** what we do locally. If it does not go upstream, the pairs are
  mostly treated as pairs that must stay together on one side of the holdout split.

## Inputs

- Agent outputs from run `sterling-2026-11-05` (`split-lists/`), copied to
  `data/identity/agent-candidates/sterling-2026-11-05/` with `SHA256SUMS`.
  - `drug-identity-links.tsv`: 242,007 drug pairs linked by name, salt words or
    InChIKey skeleton.
  - `trial-record-twin-grounding-check.tsv`: drug and disease pairs that share at
    least 10 trial records. A trial record is a (trial id, partner) pair on a
    treatment-family edge. Twin tier: mutual overlap of at least 0.9. Review tier:
    lower overlap.
- Node records exported from the 1.0.2.1 Neo4j graph: name, categories, and
  InChIKey, DrugBank, UNII and RXCUI values from `equivalent_identifiers`.

## Drug candidate set

16,128 pairs:

- identity links where both nodes have at least one treatment-family edge
  (treats, in clinical trials for, applied to treat, and their descendants, from
  any source): 12,760
- drug trial-record pairs (twin and review tiers): 6,624
- 3,263 pairs are in both.

Groups are assigned by first-pass rules. Counts are pairs, each counted once.

| source column | meaning |
|---|---|
| identity only | agent identity link; does not share 10 or more trial records |
| both | agent identity link and shares 10 or more trial records |
| trial only | in the set only because of shared trial records |

---

## A1. Same skeleton and stereo layer, differs only in protonation

**Definition.** Both nodes have at least one InChIKey. Some InChIKey of node a and
some InChIKey of node b share the first block (skeleton) and the second block
(stereo and isotope layer), and differ only in the final protonation character
(`-N` neutral, `-O` +1 proton, `-M` −1 proton, and so on). Rules checked earlier
(combination names, stereo-marked names) did not fire.

**Source.** 247 pairs: 188 identity only, 59 both, 0 trial only. Agent
categories: mostly `distinct_drug_names` (124 alone) and `salt_form` (39 alone).
69 pairs have training treatments on both nodes.

**Examples.**

- Vancomycin `MYPYJXKWCTUITO-LYRMYLQWSA-N` / vancomycin(1+) `…-O` (49 and 21 training treatments)
- Morphine `BQJCRHHNABKAKU-KBQPJGBKSA-N` / morphine(1+) `…-O` (49 and 26)
- Huperzine A `…-N` / huperzine A(1+) `…-O` (6 and 5)
- Pyruvic acid `…-N` / pyruvate `…-M`
- Calcium citrate `FNAQSUUGMSOBHW-UHFFFAOYSA-H` / CID 157010068 `…-N`

**Caveat.** In 41 pairs a node has more than one InChIKey. These are mostly
drug-chemical conflation: the graph node merges several Babel cliques, each with
its own correct key (checked against NodeNorm with conflation off):

- Choline (CHEBI:15354): choline, choline alfoscerate (glycerophosphocholine),
  choline salicylate, choline C-11
- Benzylpenicillin: plus procaine benzylpenicillin and penicillin G benzathine
- Iodine: plus iodine-131 and iodine-125
- Citric acid: plus two sodium citrate cliques
- Colistin: plus colistimethate
- Sulpyrine: plus metamizole magnesium
- Dexmethylphenidate: plus Focalin (the hydrochloride)

So choline / glycerophosphocholine lands in A1 through the conflated choline
alfoscerate key.

One looks like a real wrong key: Picibanil (CHEBI:51354, OK-432, a streptococcal
preparation) carries the benzylpenicillin anion key `JGSARLDLIJGVTE-MBNYWOFBSA-M`
in its own Babel clique, without conflation. Provenance not traced yet.

**Breakdown by which side is neutral** (`data/identity/review-2026-11-09/a1-protonation-pairs.tsv`):

| kind | pairs | training treatments on both nodes |
|---|---|---|
| one node `-N`, other charged; each node has one InChIKey | 196 | 50 |
| a node has more than one InChIKey | 30 | 17 |
| blocks match only across different keys of a multi-key node | 11 | 1 |
| neither node `-N` (e.g. cidofovir(2-) / cidofovir(1-)) | 10 | 1 |

The multi-key pairs are mostly conflated nodes (see the caveat above). They mix
clean charge pairs (Ibuprofen / ibuprofen(1-), Citric acid / citrate(3-)) with pairs
that match only through a conflated member (Choline / glycerophosphocholine).

**Decision (2026-11-09).**

- Babel: no. Charge states stay separate cliques. A conflation for them may come
  later, but not soon.
- Why it matters: these pairs are only a problem because the clinical-trials KP
  links trials to both nodes. The neutral (`-N`) form is most likely the one the
  trial meant.
- Clinical-trials KP report: pass along the 69 pairs with training treatments on
  both nodes, with the suggestion that the KP ground to the `-N` form.
- miner2049er, next graph version (whole graph, not just the candidate set):
  - Find every pair of nodes whose InChIKeys differ only in the protonation
    character, where one is `-N`.
  - Where both nodes have clinical-trials KP (`infores:multiomics-clinicaltrials`)
    edges for the same trial, keep the `-N` node's edge and drop the other
    node's edge.
  - Assumption: "same trial" means the same trial id and the same disease.
    Edges from other sources are untouched.
  - Each node is compared using only the InChIKey of its own Babel clique (the
    clique its node id belongs to, looked up without conflation). Keys brought
    in by drug-chemical conflation are ignored. This keeps clean charge pairs on
    conflated nodes (Citric acid / citrate(3-), Ibuprofen / ibuprofen(1-)) and
    drops matches that run through a conflated member (Choline /
    glycerophosphocholine).
  - Picibanil (CHEBI:51354) is excluded: its own clique carries the
    benzylpenicillin anion key, which looks wrong. Candidate Babel issue once
    the key's provenance is traced.

---

## A2. Same skeleton, different stereo layer, same name

**Definition.** Both nodes have an InChIKey. The keys share the first block
(skeleton) and differ in the second block (stereo and isotope layer). The names are
equal after lowercasing and removing punctuation (more than 5 characters), or equal
after also removing salt words. Rules checked earlier (combination names,
stereo-marked names) did not fire.

**Source.** 1,362 pairs: 812 identity only, 550 both, 0 trial only.

**Split, using each node's own-clique InChIKey** (no conflation):

| kind | pairs | training treatments on both |
|---|---|---|
| one node stereo-unspecified (`UHFFFAOYSA`), the other specified | 986 | 90 |
| both specified, different stereo | 354 | 108 |
| own keys have different skeletons; matched only through a conflated member | 22 | 13 |

**Unspecified vs specified (986).** This is the pattern 1.0.2.1 merged. The 914
unspecified nodes involved:

- 59 were marked `ambiguous` in `config/graph-1.0.2.1-replacements.tsv`
  (two or more stereoisomers): dexamethasone, tacrolimus, testosterone.
- 854 are not in that table at all. 837 of them have exactly one specified
  partner here: tirzepatide, varenicline, minocycline. The script that selected the
  table's rows is not in the repo, so why they were left out is unknown. Every
  table row has at least one clinical-trials edge on the unspecified node.

Examples: Dexamethasone `UREBDLICKHMUKA-CXSFZGCWSA-N` (275 training treatments) /
dexamethasone `…-UHFFFAOYSA-N` (132); Tirzepatide (39) / tirzepatide (36);
Testosterone (40) / testosterone (15).

**Both specified, different (354).** Several specified stereo forms of one named
drug: Tacrolimus (three keys), Everolimus (three), Exenatide (two), Amphotericin B
(two), Rifaximin (two). These are different structures.

**Matched through a conflated member (22).** Not really A2: the nodes' own keys have
different skeletons. Dexamethasone / Dexamethasone acetate, Clindamycin /
Clindamycin phosphate, Estradiol / estradiol valerate, Duloxetine / DULOXETINE
HYDROCHLORIDE. These belong with the salt and ester groups.

**Decision (2026-11-09).**

- Babel: no. A conflation of stereoisomers would be wrong, at least one applied
  across the board.
- miner2049er, graph 1.0.2.2: merge the remaining unambiguous unspecified nodes
  into their specified stereoisomer, the same way 1.0.2.1 did, by extending the
  replacement table.
  - Assumption: "unambiguous" is judged as in 1.0.2.1, by counting specified
    stereoisomers of the skeleton across the whole graph, not just partners in
    this candidate set. The 837 single-partner nodes are the starting list.
- miner2049er, holdout: the ambiguous unspecified nodes and their stereoisomers
  (dexamethasone, tacrolimus, testosterone) and the both-specified pairs
  (Tacrolimus, Everolimus, Exenatide) are real differences. Each such group goes
  entirely into train or entirely into test, never split across them.
- The 22 conflated-member pairs move to the salt and ester groups.

---

## A3. Same skeleton, different stereo layer, different names

**Definition.** As A2, but the names differ even after removing salt words.

**Source.** 1,844 pairs: 1,610 identity only, 230 both, 4 trial only.

**Split, using each node's own-clique InChIKey:**

| kind | pairs | training treatments on both |
|---|---|---|
| one node stereo-unspecified, the other specified | 861 | 194 |
| both specified, different stereo | 912 | 224 |
| own keys have different skeletons (conflated member) | 71 | 39 |

**Unspecified vs specified (861).** Mostly a racemic drug and its single-enantiomer
drug, both marketed: Medetomidine / Dexmedetomidine, Citalopram / Escitalopram,
Ketamine / Esketamine, Omeprazole / Esomeprazole, Ibuprofen / Dexibuprofen,
Ofloxacin / Levofloxacin, Bupivacaine / Levobupivacaine, Modafinil / Armodafinil,
Cetirizine / Levocetirizine, Zopiclone / Eszopiclone.

**Both specified (912).** Epimers and other stereoisomers: Dexamethasone /
Betamethasone, Ephedrine / Pseudoephedrine, Ursodeoxycholic / chenodeoxycholic acid,
Flumethasone / Diflorasone. Also same-drug variants under other names: Octreotide /
Octrotide, Acarbose / Acarbosum, Amphotericin B / Ambisome.

**Conflated member (71).** Own keys differ in skeleton: esters and salts
(Triamcinolone / triamcinolone acetonide, Prednisolone / Prednisolone-21-acetate),
Ergocalciferol / vitamin D3, insulin human / insulin glargine, and the known wrong
key aldehydo-D-idose / travoprost.

**Difference from A2.** In A2 the unspecified node had the same name as its
specified partner, which is why merging it was safe. Here the A2 merge rule would
fold racemic drugs into their enantiomer drugs (citalopram into escitalopram).

**Decision (2026-11-09).**

- Babel: no, as A2.
- miner2049er, graph: no merging.
- miner2049er, holdout: as A2. Each stereoisomer group (racemate and
  enantiomers, epimers, other stereoisomers) goes entirely into train or entirely
  into test.
- The 71 conflated-member pairs move to the salt and ester groups.

---

## A4. Different skeleton, same name

**Definition.** Both nodes have an InChIKey and no key pair shares a skeleton. The
names are equal after lowercasing and removing punctuation (more than 5
characters). Rules checked earlier did not fire.

**Source.** 465 pairs: 287 identity only, 178 both, 0 trial only. 131 have training
treatments on both nodes. All 465 still differ in skeleton when each node is
compared by its own-clique key. About half involve a `UNII:` node (FDA GSRS,
usually an upper-case name): PUBCHEM+UNII 109, CHEBI+UNII 86, UNII+UNII 24.

**Split by PubChem parent compound** (each own-clique key looked up in PubChem,
then its parent CID; `data/identity/review-2026-11-09/a4-same-name-different-structure.tsv`):

| kind | pairs | training treatments on both |
|---|---|---|
| same PubChem parent: a salt, hydrate or charge form the name doesn't mention | 83 | 30 |
| different PubChem parents | 162 | 34 |
| no single parent (mixture or polymer) | 88 | 29 |
| a key not found in PubChem | 132 | 38 |

Examples:

- Same parent: Zoledronic acid / ZOLEDRONIC ACID (monohydrate), Levofloxacin /
  LEVOFLOXACIN (hemihydrate), Theophylline / THEOPHYLLINE, Bupivacaine
  Hydrochloride / BUPIVACAINE HYDROCHLORIDE.
- Different parents: two different Tirzepatide structures, remimazolam /
  Remimazolam, Hyaluronic acid / Hyaluronic acid (different repeat units),
  beclomethasone / Beclomethasone, Fludeoxyglucose (18F) / fludeoxyglucose (18F),
  Lactulose / LACTULOSE.
- No single parent: MAGNESIUM SULFATE / Magnesium sulfate, Gentamicin / gentamicin
  (a mixture of components), growth hormone / Growth hormone (small-molecule keys on
  a protein).
- Key not in PubChem: Doxycycline (68 training treatments) / doxycycline (37),
  Minocycline (70) / Minocycline (29), Oxytetracycline / oxytetracycline, TIOTROPIUM
  BROMIDE / tiotropium bromide.

**Decision (2026-11-09).**

- Reading: mostly the name is ambiguous about which structure it means. Unlike
  charge (A1), there is no default form to prefer.
- Babel: the same-parent pairs (83) will be covered by salt conflation when it
  comes to Babel. It isn't there yet, and nothing is filed now. The rest are not
  Babel issues.
- miner2049er, graph: no change.
- miner2049er, holdout: all 465 pairs are held out or kept in training as groups,
  never split across train and test. This includes the same-parent pairs until
  salt conflation exists.

---

## A5. Different skeleton, same name after removing salt words

**Definition.** Both nodes have an InChIKey, the skeletons differ, and the names
differ but are equal after removing salt, hydrate and ester words (hydrochloride,
sodium, acetate, sulfate, hydrate, succinate, propionate and others). Also
included: 93 pairs moved here from A2 and A3, whose own-clique keys differ in
skeleton (matched earlier only through a conflated member).

**Source.** 1,382 pairs (1,289 A5 + 93 moved): 1,306 identity only, 71 both, 5
trial only. All differ in skeleton by own-clique key.

**Split by parent structure.** Each own-clique key's structure (SMILES) was fetched
from PubChem. The parent was computed with RDKit `ChargeParent` (largest fragment,
then neutralized). Note: A4 used PubChem's own parent CID instead.
`data/identity/review-2026-11-09/a5-salt-name-different-structure.tsv`.

| subgroup | kind | pairs | training treatments on both |
|---|---|---|---|
| A5a | same parent: salt, hydrate or charge form | 894 | 227 |
| A5b | parents differ only in stereo or isotope | 178 | 37 |
| A5c | different parents: ester, prodrug or other compound | 203 | 78 |

Counts corrected 2026-11-10: the batched PubChem lookup missed 27 keys that
PubChem has (diphenhydramine among them). Missing keys were re-checked one at a
time.

107 pairs (36 with training treatments on both) have no parent computed yet,
because the structure lookup found nothing for a key. They belong in A5a, A5b or
A5c. All three get the same miner2049er treatment (no graph change, group only),
so they are grouped now and sorted later.

Each subgroup is decided separately.

### A5a. Same parent

Amoxicillin / amoxicillin trihydrate, Dexmedetomidine / dexmedetomidine
hydrochloride, Ketamine / ketamine hydrochloride, Amlodipine / AMLODIPINE
BESYLATE, Atorvastatin / atorvastatin calcium.

Decision (2026-11-10), same as the A4 same-parent pairs:

- Babel: covered by salt conflation when it comes to Babel. Not there yet;
  nothing filed now.
- miner2049er, graph: no change.
- miner2049er, holdout: held out or kept in training as groups, never split
  across train and test, until salt conflation exists.

### A5b. Parents differ only in stereo or isotope

tacrolimus hydrate / tacrolimus, Tramadol / Tramadol Hydrochloride, Sugammadex /
SUGAMMADEX SODIUM, methylnaltrexone / METHYLNALTREXONE BROMIDE.

Decision (2026-11-10), as A2/A3 stereoisomers:

- Babel: no.
- miner2049er, graph: no merging.
- miner2049er, holdout: each group goes entirely into train or entirely into
  test.

### A5c. Different parents

Hydrocortisone / Hydrocortisone succinate, Metronidazole / METRONIDAZOLE
PHOSPHATE, Testosterone / testosterone sulfate, Triamcinolone / triamcinolone
acetonide, Mometasone / Mometasone furoate, insulin human / insulin glargine,
Ergocalciferol / vitamin D3.

Decision (2026-11-10):

- Babel: no. These are different compounds (esters, prodrugs, metabolites,
  analogs, vitamers).
- miner2049er, graph: no change.
- miner2049er, holdout: each group goes entirely into train or entirely into
  test.

---

## A6. Different skeleton, different names

**Definition.** Both nodes have InChIKeys, no key pair shares a skeleton, and the
names are not equal even after removing salt words. (First-pass grouping, using
all of each node's keys.)

**Source.** 554 pairs in two subgroups that came in different ways:

| subgroup | source | pairs | training treatments on both |
|---|---|---|---|
| A6a | trial only: in the set only because both nodes carry 10 or more of the same (trial, disease) records | 465 | 164 |
| A6b | agent identity links (73 identity only, 16 both) | 89 | 27 |

### A6a. Different compounds sharing trial records

Two unrelated structures that the clinical-trials KP attached to the same trials.
They form 229 connected clusters: 164 are single pairs, the largest has 11 nodes.
Largest by training treatments:

- Dexmedetomidine (158) / Detomidine (149) / Medetomidine (142): 2,645 shared
  trial records.
- Sildenafil (54) / Homosildenafil (46) / Hydromorphone 3-beta-O-glucuronide (44) /
  LODENAFIL (43) / DESMETHYLSILDENAFIL (37) / Acetildenafil (37): 891 shared trial
  records each.
- Heparin / Heparinsodiumsalt; Ofloxacin / LEVOFLOXACIN; Diclofenac /
  3-Hydroxyamino-4,6-dimethyl…; OR-1855 / Simendan / Levosimendan; Mycophenolic
  acid / Mycophenolate mofetil.

The agent's title check (is the node's name in the trial titles?): 171 pairs
neither named, 118 one named, 56 both named, 76 partial, 44 no usable words.

Decision (2026-11-10):

- Reading: mostly the two compounds share a synonym that appears in the trial
  text, and the KP assigns the trial to both rather than resolving it.
- Babel: yes. Cull ambiguous synonyms in Babel so the KP has less to trip on.
- miner2049er: nothing for now; no graph change and no holdout grouping. This is
  an exception to the usual rule that a Babel issue also gets a local fix.
- Check done after the decision: in the graph's synonym lists (first 30 per
  node), only 32 of the 465 pairs share a synonym (e.g. Arsenic trioxide / CID
  58886963, Heparin / Heparinsodiumsalt, Zinc / Velmanase alfa). Current Name
  Resolver ranks the intended node first for sildenafil and dexmedetomidine. So
  for the largest clusters the shared synonym is not visible from here; the KP
  may have used older Babel data or its own matching.

### A6b. Identity links with unrelated-looking names

The agent linked these by name or salt words; my name matching missed the link.
Re-sorted with own-clique keys and parent structures (as A5;
`data/identity/review-2026-11-09/a6b-identity-links.tsv`):

| kind | pairs | training treatments on both |
|---|---|---|
| same parent (A5a type) | 34 | 11 |
| parents differ in stereo or isotope (A5b type) | 9 | 5 |
| different parents (A5c type) | 30 | 7 |
| parent not computed (structure lookup found nothing) | 16 | 4 |

Examples:

- Same parent: Arginine / Arginine hydrochloride, Caffeine / CAFFEINE BENZOATE,
  Iodide / Sodium iodide, Nitrate / Potassium nitrate.
- Stereo: sotalol hydrochloride / DEXSOTALOL, propranolol hydrochloride /
  Dexpropranolol, CID 657263 / PROMETHAZINE, (S)-.
- Different parents: Fenofibrate / CHOLINE FENOFIBRATE, Flurbiprofen /
  Flurbiprofen axetil, lithium citrate / Lithium carbonate, Cadmium / cadmium(2+),
  TMP / TMP (two different compounds).

None is a protonation-only pair by own-clique key.

Decision (2026-11-10), same as A5:

- Babel: the same-parent pairs (34) are noted for salt conflation when it comes
  to Babel; nothing filed now. The rest are not Babel issues.
- miner2049er, graph: no change.
- miner2049er, holdout: group only. The 16 pairs without a parent yet are grouped
  now and sorted later, like the A5 leftovers.

---

## AB. Stereo-marked name vs unmarked name

**Definition.** One name carries a stereo marker ((+), (−), rac, D-, L-, R, S, cis,
trans) and the other does not, or the two carry different markers, and the names
are equal once the markers and salt words are removed. This rule ran before the
structure rules, so these pairs never reached A1–A6.

**Source.** 369 pairs: 320 identity only, 34 both, 15 trial only.

**Re-sorted with own-clique keys and parent structures**
(`data/identity/review-2026-11-09/stereo-marked-names.tsv`):

| kind | pairs | training treatments on both |
|---|---|---|
| same skeleton, different stereo, one stereo-unspecified (A2/A3 type) | 221 | 119 |
| same skeleton, both stereo-specified (A2/A3 type) | 83 | 20 |
| different skeleton, parents differ in stereo (A5b type) | 19 | 5 |
| different skeleton, same parent (A5a type) | 3 | 0 |
| different skeleton, different parents (A5c type) | 4 | 0 |
| protonation only (A1 type) | 2 | 0 |
| a node has no own-clique InChIKey (group B type) | 37 | 1 |

Examples:

- One unspecified: Atenolol / (R)-Atenolol, Venlafaxine / VENLAFAXINE, (S)-,
  Etiracetam / ETIRACETAM, (R)-, glutamine / L-Glutamine, Cycloserine /
  L-cycloserine.
- Both specified: Lipoic acid / (S)-lipoic acid, D-Glutamine / L-Glutamine,
  cis-resveratrol / Resveratrol, Abacavir / ABACAVIR, (+)-.
- A5b type: albuterol sulfate / ALBUTEROL, (+)-, FLUOXETINE HYDROCHLORIDE /
  (R)-Fluoxetine, morphine sulfate / (+)-Morphine.
- No own key: D Vitamin / VITAMIN D (75 training treatments on the smaller),
  clopidogrel sulfate / (+)-Clopidogrel, pilocarpine / (-)-pilocarpine.

**Note.** The one-unspecified pairs look like A2, but the marked name says the
specified node is one particular isomer, often of a racemic drug (atenolol,
venlafaxine). So they behave like A3, where merging would be wrong.

Decision (2026-11-10): each pair takes the decision of its type.

- A2/A3 types (304), including the one-unspecified pairs: no merging, group only
  (as A3).
- A5a/b/c types (26): as A5. No graph change, group only; same-parent pairs noted
  for future Babel salt conflation.
- A1 type (2): covered by the graph-wide A1 rule.
- Group B type (37): see "AB-B. Stereo-marked pairs without a structure" below.
- Babel: no, apart from the salt-conflation note.

---

## B1. Same name, structure missing on one or both nodes

**Definition.** At least one node has no InChIKey in the graph. The names are equal
after lowercasing and removing punctuation (more than 5 characters). No combination
or stereo-marker rule fired.

**Source.** 5,472 pairs: 3,596 identity only, 1,876 both, 0 trial only. 368 have
training treatments on both nodes.

**Own-clique keys** (current NodeNorm, conflation off):

| kind | pairs | training treatments on both |
|---|---|---|
| neither node has an own-clique key | 3,639 | 197 |
| one node has an own-clique key | 1,761 | 171 |
| both have one in current NodeNorm (none in the graph) | 72 | 0 |

The last row shows that current NodeNorm is not the Babel release the graph was
built from. Own-clique keys used in A1–AB came from current NodeNorm too.

**Who these are.** Mostly records without structures: biologics, proteins,
mixtures. Prefix pairs: UMLS+UNII 1,062, CHEMBL+UNII 981, CHEMBL+UMLS 485,
CHEBI+UMLS 392, PUBCHEM+UMLS 384, GTOPDB+UNII 306. Category pairs:
ChemicalEntity+ChemicalEntity 1,439, ChemicalEntity+SmallMolecule 1,170,
ChemicalEntity+Protein 903, Protein+SmallMolecule 665.

Examples:

- Neither keyed: botulinum toxin type A (CHEBI:3160 / UMLS:C0006050), tinzaparin
  (CHEMBL / UNII), fish oil (DRUGBANK / UNII / CHEMBL), mazdutide (UMLS / UNII),
  dalteparin (GTOPDB / UNII), fibrinogen (GTOPDB / UMLS).
- One keyed: vitamin D3 (PUBCHEM.COMPOUND:2735 / UMLS), tirzepatide (MESH /
  PUBCHEM), angiotensin II (CHEBI / PR), somatotropin (PR / UNII), enoxaparin (two
  UNIIs).

Decision (2026-11-10):

- Babel: yes, a list to take to Babel. Identifiers without structures are a real
  problem, but they exist and need cross-references. List:
  `data/identity/review-2026-11-09/babel-b1-same-name-no-structure.tsv`, now
  including the B5 pairs, the B6 chemical-record pairs and D Vitamin / VITAMIN D
  (from AB-B): 7,356 nodes in 3,039 groups (connected through same-name links, largest 8 nodes),
  sorted by training treatments. Each row has the node's category, its graph
  InChIKeys and its current own-clique key. A group can contain keyed nodes with
  different structures (tirzepatide: three keyed nodes with different keys, plus
  MeSH and UMLS records without keys).
- miner2049er, graph: no change for now.
- miner2049er, holdout: treat each group as a unit for safety, entirely in train
  or entirely in test.

---

## B2. Same name after removing salt words, structure missing on one or both

**Definition.** At least one node has no InChIKey in the graph. The names differ
but are equal after removing salt, hydrate and ester words. Includes 14 pairs
first flagged as "salt word may be the active moiety" (aspartate / magnesium
aspartate, sulfide / calcium sulfide).

**Source.** 651 pairs: 631 identity only, 15 both, 5 trial only. 62 have training
treatments on both nodes. Words removed most often: sodium 169, hydrochloride 130,
acetate 90, sulfate 64, mesylate 24.

| kind (own-clique keys, current NodeNorm) | pairs | training treatments on both |
|---|---|---|
| one node has a key | 470 | 54 |
| neither has a key | 167 | 8 |
| both have keys in current NodeNorm only | 14 | 0 |

Examples:

- One keyed: Desmopressin / desmopressin acetate (UMLS), Donepezil / donepezil
  hydrochloride, Methylphenidate / METHYLPHENIDATE HYDROCHLORIDE (UNII),
  Inclisiran / INCLISIRAN SODIUM, Pramlintide / PRAMLINTIDE ACETATE, tramadol
  hydrochloride / tramadol.
- Neither keyed: TINZAPARIN / TINZAPARIN SODIUM, dalteparin / DALTEPARIN SODIUM,
  SEVELAMER / SEVELAMER HYDROCHLORIDE, vancomycin / vancomycin hydrochloride (UMLS).
- Wrong matches from the salt-word rule, where the removed words are the drug
  itself: Potassium phosphate injection / Injection, dexamethasone injection /
  Dexamethasone Sodium Phosphate. Not counted separately.

Decision (2026-11-10), as B1:

- Babel: yes, a list to take to Babel:
  `data/identity/review-2026-11-09/babel-b2-salt-name-no-structure.tsv`, 886
  nodes in 315 groups (largest 8), same columns as the B1 list. The salt-vs-parent
  pairs are also noted for future salt conflation.
- miner2049er, graph: no change for now.
- miner2049er, holdout: each group is a unit, entirely in train or entirely in
  test.

---

## B3. Ingredient vs dose-form product

**Definition.** One name is the other plus dose-form words (injection, oral,
topical, cream, solution, intravenous, product, gel, patch, capsule, tablet and
others). The longer-named node is a product record: 194 of 206 are UMLS, 9 RXCUI.
None of the product nodes has an InChIKey.

**Source.** 206 pairs: 198 identity only, 8 both. 29 have training treatments on
both nodes.

**Relation.** Two kinds, not counted separately:

- Ingredient vs a product of that ingredient (most): Testosterone / Testosterone
  Gel, Ibuprofen / Ibuprofen Injection, Liraglutide / Liraglutide Injection,
  Estradiol / Estradiol Patch, Tranexamic acid / tranexamic acid topical, EMLA /
  EMLA Cream. 106 pairs have a keyed ingredient node; in 100 neither node is keyed.
- Class vs a route-specific part of the class: Anticoagulants / oral
  anticoagulants, Immunoglobulins / immunoglobulins, intravenous, corticosteroid /
  corticosteroid injection, Infusion procedures / Intravenous infusion procedures
  (a procedure, not a drug).

Decision (2026-11-10):

- Babel: yes. Drug-chemical conflation should join a product to its ingredient,
  and it doesn't for any of these. List to work out why:
  `data/identity/review-2026-11-09/babel-b3-dose-form-not-conflated.tsv`, one
  row per pair with each node's conflated id (current NodeNorm, conflation on) and
  the number of RXCUIs in its conflated clique.
  - All 206 pairs get different conflated ids.
  - 192 product nodes have no RXCUI in their clique, which fits conflation
    running through RxNorm. The other 14 have RXCUIs and are still not joined.
- miner2049er, graph: no change.
- miner2049er, holdout: grouped.

---

## B4. Combination products

**Definition.** At least one name is a combination (ingredients joined by "/",
"+", "&", "and", "with" or a hyphen), and the two ingredient sets are compared
after removing salt words and filler words (regimen, protocol, combination).

**Source.** 71 pairs: 53 identity only, 2 both, 16 trial only. 8 have training
treatments on both nodes. Drug-chemical conflation (current NodeNorm) joins none.

**Relations:**

- Same combination, different records (59; 29 with no key on either node):
  dorzolamide / timolol vs Dorzolamide Hydrochloride / Timolol Maleate, amlodipine /
  benazepril, fluticasone / salmeterol, ceftolozane / tazobactam, buprenorphine /
  naloxone, oxycodone / acetaminophen. Mostly MESH or PUBCHEM vs UMLS records.
  Includes regimens: lomustine / procarbazine / vincristine vs PCV regimen,
  gemcitabine / oxaliplatin.
- Combination vs one of its ingredients (12): Buprenorphine vs Buprenorphine +
  naloxone, Omeprazole vs omeprazole / sodium bicarbonate, Tiotropium vs
  olodaterol / tiotropium bromide, VITAMIN D vs calcium carbonate / vitamin D,
  Cisplatin vs Cantide + Cisplatin. Four of the 12 are wrong matches: CHOP protocol
  vs CHOP regimen (actually the same regimen), two allogeneic stem cell transplant
  records (procedures), Aromatherapy vs Aromatherapy and Essential Oils, a
  norepinephrine reuptake inhibitor class vs a dopamine-and-norepinephrine one.

Decision (2026-11-10):

- Same combination, different records (59, plus CHOP protocol / CHOP regimen
  moved here = 60 pairs):
  - Babel: yes, a list. Conflation joins none of them:
    `data/identity/review-2026-11-09/babel-b4-same-combination.tsv`, 108 nodes in
    50 groups, with each node's conflated id.
  - miner2049er: no graph change; grouped in the holdout.
- Combination vs one of its ingredients (8 real pairs): related but distinct, as
  A5c.
  - Babel: no.
  - miner2049er: no graph change; grouped in the holdout.
- Wrong matches (3: the two allogeneic stem cell transplant records, Aromatherapy
  / Aromatherapy and Essential Oils, the two reuptake-inhibitor classes): no
  action and no grouping.

---

## B5. Same words in a different order

**Definition.** The names have the same words after lowercasing and removing
punctuation, in a different order. At least one node has no InChIKey.

**Source.** 24 pairs, all identity links (1 also shares trial records). Only 2
have training treatments on both nodes. Drug-chemical conflation joins none.

**Relation.** The same concept with an inverted heading, typically a MeSH, ChEMBL
or UNII record vs a UMLS record: insulin human / human insulin, interferon gamma /
gamma-interferon, STARCH, POTATO / potato starch, Saliva, Artificial / Artificial
saliva, Esterified estrogens / ESTROGENS, ESTERIFIED, Docetaxel (Taxotere) /
Taxotere® (Docetaxel). Some are classes rather than drugs: Drugs, Generic /
Generic Drugs; Contraceptives, Oral, Combined / Combined Oral Contraceptives;
PROTECTANT, SKIN / Skin Protectant. This is the B1 relation (same concept,
structure missing on a side) with a reordered name.

Decision (2026-11-10): folded into B1. The 24 pairs are added to the B1 Babel
list and grouped in the holdout with B1.

---

## B6. Short identical names

**Definition.** Names equal after lowercasing and removing punctuation, 5
characters or fewer. Kept apart from B1 because short names collide.

**Source.** 344 pairs: 252 identity only, 92 both. 13 have training treatments on
both nodes.

**Relations** (gene = NCBIGene/PR/UniProtKB record; taxa from current NodeNorm):

| relation | pairs | training treatments on both |
|---|---|---|
| the same gene symbol in different species (orthologs) | 206 | 5 |
| same-name chemical or product records | 120 | 7 |
| a gene vs a chemical record that shares the symbol | 16 | 1 |
| two different genes with the same symbol in one species | 2 | 0 |

Examples:

- Orthologs: Ptgs2 mouse (NCBIGene:19225) / PTGS2 human (NCBIGene:5743) / Ptgs2
  rat, Thrsp / THRSP, Rala / RALA, nuf2 zebrafish / Nuf2 mouse / NUF2 human. These
  genes carry treatment-family edges, likely trial interventions grounded to genes.
- Chemical or product records: IL-23 (GTOPDB / UNII), COX-2 (CHEMBL / UNII), VSL#3
  (UMLS / UNII), Zosyn (PUBCHEM / UMLS), Elmex, cocoa, herbal products (qishe,
  sanqi, fusio; MESH / UMLS).
- Gene vs chemical: Tea (MESH) / tea (fly gene), NPPB chemical / NPPB human gene,
  PAC-1 / pac-1 worm gene, SNP / Snp fly gene.
- Same species: SR1 / SR1 (two Arabidopsis genes), BaRF1 / BARF1.

Decision (2026-11-11):

- Same-name chemical or product records (120): as B1. Added to the B1 Babel list
  and grouped in the holdout.
- Cross-species orthologs (206), gene vs chemical homonyms (16), same-species
  gene collisions (2): different things. Not Babel issues, no graph change, no
  grouping.

---

## AB-B. Stereo-marked pairs without a structure

**Definition.** The 37 stereo-marked-name pairs (from AB) where at least one node
has no own-clique InChIKey, so the stereo relation can't be checked by structure.

**Relations** (read from the names):

| relation | pairs | examples |
|---|---|---|
| same compound, a stereo form named on one side | 21 | Clopidogrel / (+)-Clopidogrel, Repaglinide / (-)-repaglinide, BORNEOL / (-)-borneol, pilocarpine / (-)-pilocarpine, selenomethionine / L-Selenomethionine, ribose / D-ribose, cyclopentolate (±) forms, Abacavir / (+)-Abacavir |
| a salt form plus a stereo form | 9 | clopidogrel sulfate / (+)-Clopidogrel, abacavir sulfate / (+)-Abacavir, Morphine Chloride / (+)-Morphine, L-lysine hydrochloride / lysine, L-threonic acid / its magnesium salt |
| not a stereo marker: "D" in vitamin D | 1 | D Vitamin / VITAMIN D (78 and 75 training treatments) |
| combination vs one ingredient | 2 | CALCIUM CITRATE/VITAMIN D / VITAMIN D, CALCIUM/VITAMIN D / VITAMIN D |
| related solutions | 3 | Ringer's lactate, Ringer's acetate / RINGER'S |
| different products | 1 | Oshadi D / Oshadi R |

Note: marketed abacavir is the (−) enantiomer, so (+)-Abacavir is a different
isomer, not a relabelling.

Decision (2026-11-11):

- Stereo only (21) and salt plus stereo (9): no graph change, group only (as
  A2/A3 and A5b). Not Babel issues.
- D Vitamin / VITAMIN D: added to the B1 Babel list and grouped.
- Combinations with vitamin D (2): grouped, as B4.
- Ringer's solutions (3): grouped.
- Oshadi D / Oshadi R: different products; no action, no grouping.

---

## Trial text for the charge and stereo lists

Added 2026-11-12 for passing to the clinical-trials KP. Each list in
`data/identity/review-2026-11-09/` now has summary columns (`ct_trials_a`,
`ct_trials_b`, `shared_trials`, `original_subjects_a`, `original_subjects_b`) and a
companion `*-shared-trials.tsv` with one row per pair and shared trial.

| list | pairs | pairs sharing a trial | pair-trial rows |
|---|---|---|---|
| `a1-protonation-pairs` | 247 | 191 | 7,073 |
| `a2-stereo-pairs` | 1,340 | 1,232 | 23,474 |
| `a3-stereo-pairs` | 1,773 | 750 | 15,660 |
| `stereo-marked-names` | 369 | 124 | 2,775 |

Each shared-trial row has the NCT id and title, the intervention text, each
side's `original_subject` (the CURIE the KP emitted before normalization), the
diseases each side links to for that trial, and the KP's tested-intervention flag.

- Graph trial edges carry `original_subject` and the trial (id, title, phase,
  tested-intervention flag) but not the intervention text.
- Intervention text comes from the ClinicalTrials.gov API v2, fetched
  2026-11-12 (`data/identity/ctgov-interventions-2026-11-12.json`, 28,501 trials;
  one not returned). AACT's database needs a login; this is the same registry but
  the current version, which may differ from the KP's snapshot.
- Trial edges for the review nodes: `data/identity/ct-edges-review-nodes.jsonl`.
- Example: in NCT00000574 ("Ibuprofen in Sepsis Study", intervention "ibuprofen
  [DRUG]") the KP emitted both CHEBI:5855 (Ibuprofen) and CHEBI:132922
  (ibuprofen(1-)) as subjects.

---

## C. Trial-grounding pairs, regrouped by relation

**Source.** The first pass had two groups here: interventions grounded to a
stand-in node (577 pairs) and trial-record pairs with no name or structure
evidence (2,602). They are regrouped by the relation between the two nodes
(`data/identity/review-2026-11-09/group-c-relations.tsv`). A stand-in is a node
whose name marks it as an assay or measurement, an [EPC] class, a drug class, or
a billing code ("INJECTION, X, 500 MG ADMINISTERED"); detected by name.

| relation | pairs | training treatments on both | trial only | identity link |
|---|---|---|---|---|
| C-R1 substance vs a stand-in for it | 686 | 312 | 394 | 292 |
| C-R2 stand-in vs stand-in | 95 | 38 | 78 | 17 |
| C-R3 same concept by synonym (code name, brand) | 144 | 41 | 144 | 0 |
| C-R4 gene or protein vs a chemical or biologic | 409 | 82 | 408 | 1 |
| C-R5 gene or protein vs gene or protein | 293 | 28 | 293 | 0 |
| C-R6 a procedure or generic concept involved | 174 | 29 | 161 | 13 |
| C-R7 chemical vs chemical, no evidence of a relation | 1,378 | 282 | 1,374 | 4 |

Examples:

- R1: Acetaminophen / Acetaminophen measurement, VITAMIN D / Vitamin D Drug Class,
  Azithromycin / INJECTION, AZITHROMYCIN, 500 MG, vitamin C / Vitamin C [EPC].
- R2: Vitamin D measurement / Vitamin D [EPC] / Vitamin D Drug Class; Insulin
  measurement / Insulin [EPC] / Insulin Drug Class.
- R3: Liraglutide / NN 2211, rhuMAb-E25 / Omalizumab, SGN-35 / Brentuximab
  vedotin, Oxytocin / Syntocinon, Methotrexate / Maxtrex. The name of one is in
  the other's synonym list (first 30 synonyms only).
- R4: GH1 / somatropin, OXT / Oxytocin, Etanercept / TNF receptor superfamily
  member.
- R5: AGT / angiotensin II, lactotransferrin / LTF protein, human, ARID3B / Pcsk1.
- R6: Therapeutic procedure / Administration (procedure), Pharmacotherapy /
  Chemotherapy, Oxcarbazepine / DRUG SCREEN QUANTITATIVE OXCARBAZEPINE.
- R7: 24,25-Dihydroxyvitamin D / VITAMIN D, Melatonin / Recombinant melatonin,
  IDEC-C2B8 Antibody / Rituximab, co-trimoxazole / Trimethoprim-Sulfamethoxazole.
  Mixed: includes same-concept pairs the 30-synonym check missed.

Decisions per relation: _pending_
