# fixture for extract_tcl
source ./lib/helpers.tcl

namespace eval myns {
    proc greet {name} {
        puts "hi $name"
    }
}

proc main {} {
    greet world
}
