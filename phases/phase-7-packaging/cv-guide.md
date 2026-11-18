# The CV after the capstone

Week 27, step 2 of the [study plan](../../README.md#week-27-the-public-write-up-and-the-cv): a new CV that starts with the target title and the numbers of the project. This page says what goes first and which numbers to quote. It has no example CV, because the CV holds your own history. Keep the CV out of the repository.

## What goes first

1. **The target title**, as the job listings write it, for example "AI Engineer" or "Applied AI Engineer". Use the title of the roles that you apply for, not your current title.
2. **A summary of two lines** that names the role and the evidence: the kind of system that you built (a production agent with evaluation, retrieval, guardrails and a self-hosted model), and the years of software engineering behind it. The plan says: "Add a two-line summary naming the role".
3. **The AI work at the top of your current job.** If you did AI work at your employer, put it first under that job, with the numbers that you may make public. If you did not, put the capstone project directly under the summary, as a project with its own heading and the link to the repository.
4. **The software engineering experience after it.** Senior AI roles ask for systems experience: services, databases, CI, on-call. Keep the lines that show it.

## Which numbers to quote

Quote the numbers of the table in `docs/writeup.md`. Each one has a result file, so you can show where it comes from in an interview. `make numbers` prints them again.

| Claim on the CV | Number from the table | Say with it |
| --- | --- | --- |
| The agent is tested | Test set size, task success rate | The number of cases and the share in Arabic |
| Retrieval is measured | Retrieval recall, English and Arabic | The method that gave it (for example hybrid search with a re-ranker) and the k of recall@k |
| The grader is trusted | Grader agreement with your labels | The two rates and the number of labels |
| The system resists attacks | Attack-suite pass rate | The number of attacks and that the suite runs in CI |
| The system is observed | 95th-percentile latency, cost per request | Where you measured it (your machine, the model) |
| You can run open models | Hosted against self-hosted model | Quality, latency and cost per 1,000 requests of each |

Rules for each number:

- **Give the context in the same line.** A rate without its sample size means little. "Task success 0.82 on 105 cases" is a claim that a reader can check.
- **Quote only what you measured.** If a run used a small sample or a fake model, do not quote it as a quality result.
- **Use the same value as the write-up.** The exit test asks you whether the CV and `docs/writeup.md` agree.
- **Do not claim real users that you do not have.** If a team used the system, give the number of people and what they did with it. The plan says that real users are the strongest evidence.

## What to leave out

- Employer data, internal names and numbers that your employer did not agree to make public.
- Tools that you only read about. The plan leaves out Kubernetes and a second cloud: do not list them because of this project.
- A list of every library. Name the main parts (Claude API, LangGraph, MCP, pgvector, Langfuse, LiteLLM, vLLM) and let the repository show the rest.

## Before you send it

- Open the repository link of the CV in a browser where you are signed out. It must open.
- Compare each number of the CV with `docs/writeup.md`.
- Read the CV against two or three listings of the target role. The words of the listing for the same skill help a reader find it.
