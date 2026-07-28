# R fixture: top-level bare calls with no own definition and no source() link,
# so `dup()` is ambiguous (defined in r_other.R and r_extra.R) and `helper()`
# resolves INFERRED to a single unique cross-file candidate.
dup()
helper()