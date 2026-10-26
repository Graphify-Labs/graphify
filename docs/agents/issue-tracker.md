# Issue tracker: GitHub

Issues and specs live in `JulioLeonPhD/graphify`.
Use the gh CLI with explicit `--repo JulioLeonPhD/graphify`;
do not infer the target from this clone's multiple remotes.

MATLAB wayfinding: [Find the smallest maintainer-ready MATLAB extractor PR](https://github.com/JulioLeonPhd/graphify/issues/1).
The map links the migrated research evidence; its native sub-issues are the decision tickets.

## Upstream PR boundary

This tracker configuration is fork-local. Before opening the MATLAB extractor PR
against Graphify-Labs/graphify, remove this file and the fork-specific Issue tracker
subsection in AGENTS.md from the upstream PR diff. Do not replace the destination
with upstream and publish fork planning issues there. Keep local planning artifacts
out of the upstream PR.

## Operations

- Create: `gh issue create --repo JulioLeonPhD/graphify --title "..." --body "..."`
- Read: `gh issue view <number> --repo JulioLeonPhD/graphify --json number,title,body,labels,comments,assignees`
- List: `gh issue list --repo JulioLeonPhD/graphify --state open --json number,title,body,labels,assignees`
- Comment: `gh issue comment <number> --repo JulioLeonPhD/graphify --body "..."`
- Label: `gh issue edit <number> --repo JulioLeonPhD/graphify --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --repo JulioLeonPhD/graphify`

When a skill says publish or fetch a ticket, create or read a GitHub issue.

## Pull requests as a triage surface

PRs as a request surface: no.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`.
- Tickets: native sub-issues of the map, labelled `wayfinder:<type>`.
  Map and tickets carry only wayfinder labels, not triage labels.
- Parent link: POST `repos/JulioLeonPhD/graphify/issues/<map>/sub_issues`
  with `sub_issue_id=<child database id>`, using `gh api`.
- Blocking: native GitHub issue dependencies. POST
  `repos/JulioLeonPhD/graphify/issues/<child>/dependencies/blocked_by`
  with `issue_id=<blocker database id>`. Use database ids, not issue numbers.
- Frontier: query the map's sub-issues; select open, unassigned tickets
  with no open blockers. Preserve sub-issue order.
- Claim before work: assign the ticket to `@me`.
- Resolve: post a resolution comment, close the ticket, then append
  a named link and one-line gist to the map's Decisions so far.
- Refer to maps and tickets by linked title, never a bare number.

Only if native relationships are unavailable: use a task list on the map,
a parent link on each child, and a Blocked by line linking blockers.
