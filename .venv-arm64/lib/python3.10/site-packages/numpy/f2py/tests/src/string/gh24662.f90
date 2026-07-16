subroutine string_inout_optional(output)
    implicit none
    character*(32), optional, intent(inout) :: output
    if (present(output)) then
      output="output string"
    endif
end subroutine
