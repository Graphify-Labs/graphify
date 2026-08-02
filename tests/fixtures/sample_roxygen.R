#' Build a moments container
#'
#' @param x numeric vector
#' @template param-shared
#' @seealso \code{\link{summarise_moments}} for the reporting side
#' @family moments
#' @export
new_moments <- function(x) {
  structure(list(x = x), class = "moments")
}

#' Restore the class after a transformation
#'
#' A second site that assigns the same class - the constructor convention is
#' what tells resolution which one creates the object.
reattach_moments <- function(obj) {
  class(obj) <- "moments"
  obj
}

#' @export
print.moments <- function(x, ...) {
  cat("moments\n")
}

#' A generic with a real UseMethod declaration
#' @export
describe <- function(x, ...) UseMethod("describe")

describe.moments <- function(x, ...) {
  invisible(x)
}

# Not documented, not exported, and an ordinary dotted name: nothing in the
# corpus evidences a `my` generic or a `helper` class, so no method edge.
my.helper <- function(x) x + 1

summarise_moments <- function(m) length(m$x)
