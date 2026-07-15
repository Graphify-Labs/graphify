# Graphify R fixture: exercises every construct the extractor handles.
# Function assignment forms (left, super, equals, right, super-right):
library(dplyr)
requireNamespace("utils")
library(installed.packages())          # dynamic arg -> NO import edge
source("r_other.r")                    # static source() -> imports_from edge

foo <- function(x) {                   # `<-` form
  helper()                             # cross-file call (defined in r_other.R)
  print(x)                             # builtin in raw_calls
}

bar <<- function(y) y * 2              # `<<-` super-assignment form

baz = function(z) {                    # `=` form
  inner <- function(w) {               # nested function
    helper()                           # attributed to inner, not baz
    z + w
  }
  inner(z)                             # same-file call -> EXTRACTED
}

function(a) a + 1 -> qux              # `->` right-assignment form
function(b) b * 2 ->> quux           # `->>` super-right-assignment form

# Member calls (do NOT resolve via the bare-name resolver):
obj$method()
obj@field()

# Package-qualified calls (recorded as member raw_calls; pkg import edge emitted):
base::summary()
dplyr::filter()
utils:::deep_fn()

# Pipes (traversed so contained calls are captured):
1 |> qux() |> foo()
"data" %>% process() %>% save()

# Named call argument with `=` is NOT a function definition:
options(config = function() 42)

# Top-level call (attributed to the file node):
foo(1)