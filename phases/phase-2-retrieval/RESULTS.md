# Phase 2 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them. Write the machine on which you measured the times, for example "MacBook Pro, M3, 16 GB".

Machine:

## Week 4: parsing and chunking

The 5 Arabic PDFs that you read, and what each parser gave.

| Document | Pages read | PyMuPDF: faults found | Docling: faults found (if you tried it) |
| --- | --- | --- | --- |
| | | | |
| | | | |
| | | | |
| | | | |
| | | | |

| Measure | Value |
| --- | --- |
| Parser that you kept, and why | |
| Chunk size and overlap (words) | |
| Documents ingested | |
| Chunks stored, Arabic | |
| Chunks stored, English | |
| Time of `make ingest` | |

## Week 5: vector search

| Measure | Value |
| --- | --- |
| Time of the first `make up` (model download) | |
| Time of `make embed` | |
| Time of one vector search (s) | |
| The plan uses the HNSW index with `enable_seqscan = off` (yes or no) | |

Recall in the top five, from `make recall ARGS="--modes vector"`.

| Mode | Arabic | English | All |
| --- | --- | --- | --- |
| vector | | | |

Questions that the vector search misses, by cause.

| Cause | Arabic | English |
| --- | --- | --- |
| The expected chunk ID was wrong | | |
| The question uses other words than the document | | |
| Many chunks look the same | | |
| Other | | |

## Week 6: hybrid search and re-ranking

| Measure | Value |
| --- | --- |
| Text search configuration for Arabic | |
| Text search configuration for English | |
| Time of one hybrid search (s) | |
| Time of one search with re-ranking (s) | |
| Time of `make recall` with the three modes | |

Recall in the top five, from `make recall`.

| Mode | Arabic | English | All |
| --- | --- | --- | --- |
| vector | | | |
| hybrid (rank fusion) | | | |
| hybrid + re-ranking | | | |
| keyword search alone (from the notebook) | | | |

Differences between the modes, from the rows of `evals/results/recall.json`.

| Measure | Arabic | English |
| --- | --- | --- |
| Questions that hybrid finds and vector misses | | |
| Questions that vector finds and hybrid misses | | |
| Questions that re-ranking finds and hybrid misses | | |
| Questions that hybrid finds and re-ranking misses | | |

Your explanation of the differences, in a few sentences:

## Week 7: the live check

From `make check-live WEEK=7`. Date of the run:

| Question | Expected chunk cited | Citations | Requests | Cost (USD) | Errors |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

| Measure | Value |
| --- | --- |
| Total cost (USD) | |
| Answers rejected for a wrong citation | |

## Exit test: recall before and after hybrid search and re-ranking

From `make recall` with your final code, 50 questions, top five. Date of the run:

| Mode | Arabic | English | All |
| --- | --- | --- | --- |
| vector | | | |
| hybrid (rank fusion) | | | |
| hybrid + re-ranking | | | |
