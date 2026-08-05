# The self-hosted benchmark runner

Six benchmarks cannot run on a GitHub-hosted runner, because each needs a
tool no hosted runner can install: ORCA (registration-gated), AutoDock Vina,
the 152 MB nmrshiftdb2 index, and the two multi-hundred-MB sidecar
environments. A machine that already has them can run all six.

This page is the honest answer to "what does registering a runner actually
give GitHub control over", and then the setup.

## What a self-hosted runner IS, precisely

A program you install and start. It polls GitHub, and when a job is assigned
to it, **it executes that workflow's steps on your machine as whatever user
the runner process is running as** — with that user's filesystem access,
network access, installed programs, and credential store.

There is no sandbox. That is not a flaw being glossed over; it is what a
self-hosted runner is for. The safety therefore comes entirely from
controlling **who can cause a job to be sent to it**.

## Why this is safe here, and the one rule that makes it so

**This repository is PUBLIC.** GitHub's own guidance is to use self-hosted
runners only with private repositories, because on a public repo anybody can
fork it, open a pull request whose workflow runs on your runner, and execute
arbitrary code on your machine.

That risk closes completely under one rule:

> **The self-hosted workflow must NEVER have a `pull_request` trigger.**

`workflow_dispatch` and `schedule` both run the workflow file **from the
default branch**, and neither can be fired by a fork. So only somebody with
**write access to this repository** can send a job to your machine — which
today is you.

`benchmarks-selfhosted.yml` has `workflow_dispatch` only, plus a repository
guard so the job refuses to start on a fork. If you ever add a
`pull_request` trigger to it, you have handed shell access on your machine
to anybody on the internet with a GitHub account. There is no partial
version of this.

## What remains true even so

- Anybody you grant **write access** to this repository can run code on the
  runner machine. Collaborators are trusted with the machine, not just the
  code.
- If your **GitHub account is compromised**, the attacker gets code
  execution on that machine.
- A workflow file on `master` can be changed, and the runner will run the
  changed version.

## Two settings that shrink the exposure to near zero

**1. Run it as a dedicated local user, not as yourself.** This is the
single most valuable step. Create a standard (non-admin) Windows account
that owns nothing, and run the runner as that user. A job then cannot read
your documents, your SSH keys, or the OS keychain where the AI assistant
plugin stores API keys. It still needs read access to the ORCA and Vina
installs and somewhere to write scratch files.

**2. Do NOT install it as an always-on service.** Start it by hand when you
want a benchmark run and stop it with Ctrl-C afterwards. Jobs are manual
anyway, so an always-listening agent buys nothing, and the machine is then
only reachable during a window you personally opened.

Removing it entirely is one command, any time:

```bash
cd actions-runner
./config.cmd remove --token <REMOVAL_TOKEN>
```

## Setup

Get a registration token — it is short-lived and scoped to this repository:

```bash
gh api -X POST repos/xaerogonzo/OpenChem-Studio/actions/runners/registration-token --jq .token
```

Then, in a directory outside the repository:

```bash
mkdir actions-runner && cd actions-runner
curl -o runner.zip -L https://github.com/actions/runner/releases/latest/download/actions-runner-win-x64.zip
tar -xf runner.zip
```

Configure it. **The labels matter**: the workflow targets
`[self-hosted, windows, openchem-tools]`, and that last label is what stops
a job landing on some other self-hosted machine that has no ORCA:

```bash
./config.cmd --url https://github.com/xaerogonzo/OpenChem-Studio \
             --token <REGISTRATION_TOKEN> \
             --labels openchem-tools \
             --unattended
```

Start it for a run, and stop it after:

```bash
./run.cmd
```

## What the runner machine needs

The workflow does not install any of these; it fails the relevant step and
carries on, so a partly-equipped machine still produces the benchmarks it
can. Each step reports what it could not find.

| tool | used by | notes |
|---|---|---|
| ORCA + `orca_plot` | `ir`, `esp`, `nmr` | must be on a space-free path |
| AutoDock Vina | `docking` | plus the cached receptor library |
| nmrshiftdb2 index | `nmr` | the 152 MB download |
| ADMET-AI sidecar | `admet` | ~1 GB environment |
| pkasolver sidecar | `pka` | its own environment |
| Temurin JRE | naming round-trips | OPSIN shells out to a bare `java` |

Paths come from the same `Settings` store the application uses, so a machine
where the app already works needs no extra configuration.
