module typedefmod
  use iso_fortran_env, only: real32
end module typedefmod

module data
  use typedefmod, only: real32
  implicit none
  real(kind=real32) :: x
  common/test/x
end module data
