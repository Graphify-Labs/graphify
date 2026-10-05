## What does this PR do?

<!-- Describe the problem and the change. Link the relevant issue when one exists. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Tests or CI
- [ ] Refactor
- [ ] Security fix

## Verification & Invariants

<!-- What invariant does this code protect? How do you prove your change doesn't break it? What generated or persisted state could your change invalidate? -->

- [ ] **Read** the [CONTRIBUTING.md](../CONTRIBUTING.md) guide.
- [ ] **Reproduced** the issue and identified the invariant.
- [ ] Made the **smallest fix** necessary.
- [ ] Added a **regression test** (if bug fix) or isolated boundary test.
- [ ] Kept the PR description **synchronized** with the final implementation.
- [ ] Documented any **limitations / unsupported cases** explicitly.

## How was this tested?

<!-- List the commands you actually ran. Mention environment isolation if touching provider paths. -->

```text

```

## Graphify-specific checklist

- [ ] I updated generated skill artifacts (`uv run python -m tools.skillgen --bless`) when changing their source fragments.
- [ ] I confirmed that AST/structural extraction remains deterministic (no ambient state dependencies like ENV variables).
- [ ] I reviewed changes for security implications (no unsafe interpolation into shell/Python).
- [ ] I confirmed no API keys or local-only graph data are included.
- [ ] (If applicable) I disclosed AI authorship in my commit messages.
