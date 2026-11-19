# Reference solutions

This branch holds the reference solution of each lab week. Each week of the plan has one commit, and the commits are on top of `main` in the order of the weeks.

The commit of week N holds the files that you own at the end of week N. These are the starter files of each phase that you started (as `make start PHASE=n` copies them), and the code and the files of the reference solution of each week up to week N.

Try each week yourself first. Look at the reference only after you finish your own work, or when you are stuck.

## See one week

The list of the commits, one for each week:

```bash
git log --oneline solutions
```

The changes of one week are the difference between its commit and the commit of the week before. For week 1, use `main` as the commit of the week before.

```bash
git diff <commit of week N-1>..<commit of week N>
```

## The checks

On the commit of each week N, `make check WEEK=N` passes. On the last commit of each phase, `make check PHASE=n` also passes for that phase and for each earlier phase. The checks need the services and the data that the guide of each phase tells you to start and load.

The folder `evals/results/` is in `.gitignore`. The branch holds only the result files that a check or a document reads, added with `git add -f`.

The reference write-up `docs/writeup.md` names the address of this repository, https://github.com/ishassan/ai-engineer-study-plan. The week 27 check compares the address in the write-up with `git remote get-url origin`. In a fork, write the address of your fork.
