# Sample R file exercising the graphify R extractor (#1689).
# Covers: library/require imports, source(), function definitions via
# <-, =, <<- and the \(x) lambda shorthand, S4 classes with inheritance,
# generics, methods, and intra-file call edges.

library(dplyr)
require(ggplot2)
source("helpers.R")

# --- plain functions -------------------------------------------------------

distance <- function(p, q) {
  dx <- p$x - q$x
  dy <- p$y - q$y
  sqrt(square(dx) + square(dy))
}

square = function(n) {
  n * n
}

# super-assignment binding
resetCache <<- function() {
  invisible(NULL)
}

# R 4.1 lambda shorthand
double <- \(x) x * 2

# --- S4 object system ------------------------------------------------------

setClass("Shape", representation(name = "character"))
setClass("Circle", contains = "Shape", representation(radius = "numeric"))

setGeneric("area", function(obj) standardGeneric("area"))

setMethod("area", "Circle", function(obj) {
  square(obj@radius) * 3.14159
})
