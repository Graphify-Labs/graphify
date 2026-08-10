#' Sample R file exercising the shapes extract_r has to handle.
library(stats)
requireNamespace("jsonlite")
source("sample_helper.R")
source(file.path("tests", "fixtures", "sample_helper.R"))

compute_moments <- function(x, weights = NULL) {
  scaled <- rescale(x)
  total <- sum(scaled)
  normalise_weights <- function(w) w / sum(w)
  if (!is.null(weights)) {
    total <- total * sum(normalise_weights(weights))
  }
  total
}

rescale = function(x) {
  x / stats::sd(x)
}

report_moments <- \(x) {
  cat(format_row(x))
}

cache_result <<- function(value) {
  invisible(value)
}

# Parenthesised: `function(x) x^2 -> nm` would bind nm INSIDE the body instead.
(function(x) x^2) -> square_it

summarise <- function(items) {
  vapply(items, function(item) compute_moments(item), numeric(1))
}

compute_moments(c(1, 2, 3))
