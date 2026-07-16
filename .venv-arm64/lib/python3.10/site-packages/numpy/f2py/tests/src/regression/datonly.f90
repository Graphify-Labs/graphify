module datonly
  implicit none
  integer, parameter :: max_value = 100
  real, dimension(:), allocatable :: data_array
end module datonly

module dat
  implicit none
  integer, parameter :: max_= 1009
end module dat

subroutine simple_subroutine(ain, aout)
  use dat, only: max_
  integer, intent(in) :: ain
  integer, intent(out) :: aout
  aout = ain + max_
end subroutine simple_subroutine
