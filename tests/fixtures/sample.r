library(
  package = dplyr
)
requireNamespace("jsonlite")

normalize_values <- function(
  values,
  trim = 0
) {
  mean(values, trim = trim)
}

identity_value <<- function(value) value

make_scaler <- function(scale) {
  scale_one <- function(value) {
    value * scale
  }
  scale_one(scale)
}

analyze <- function(values) {
  normalized <- normalize_values(values)
  identity_value(normalized)
  stats::median(normalized)
}

# Calls in comments and strings are not executable dependencies:
description <- "normalize_values(fake)
fake <- function(value) {
  identity_value(value)
}"
