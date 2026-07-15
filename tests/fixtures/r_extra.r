# R fixture: defines a second `dup` (ambiguity with r_other.R) and a no-source
# caller scope, so `helper()` resolves INFERRED unless source() linkage exists.
extra_fn <- function() {
  helper()
}

dup <- function() {
  NA
}