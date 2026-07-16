! Check that parameter arrays are correctly intercepted.
subroutine foo_array(x, y, z)
  implicit none
  integer, parameter :: dp = selected_real_kind(15)
  integer, parameter :: pa = 2
  integer, parameter :: intparamarray(2) = (/ 3, 5 /)
  integer, dimension(pa), parameter :: pb = (/ 2, 10 /)
  integer, parameter, dimension(intparamarray(1)) :: pc = (/ 2, 10, 20 /)
  real(dp), parameter :: doubleparamarray(3) = (/ 3.14_dp, 4._dp, 6.44_dp /)
  real(dp), intent(inout) :: x(intparamarray(1))
  real(dp), intent(inout) :: y(intparamarray(2))
  real(dp), intent(out) :: z

  x = x/pb(2)
  y = y*pc(2)
  z = doubleparamarray(1)*doubleparamarray(2) + doubleparamarray(3)

  return
end subroutine

subroutine foo_array_any_index(x, y)
  implicit none
  integer, parameter :: dp = selected_real_kind(15)
  integer, parameter, dimension(-1:1) :: myparamarray = (/ 6, 3, 1 /)
  integer, parameter, dimension(2) :: nested = (/ 2, 0 /)
  integer, parameter :: dim = 2
  real(dp), intent(in) :: x(myparamarray(-1))
  real(dp), intent(out) :: y(nested(1), myparamarray(nested(dim)))

  y = reshape(x, (/nested(1), myparamarray(nested(2))/))

  return
end subroutine

subroutine foo_array_delims(x)
  implicit none
  integer, parameter :: dp = selected_real_kind(15)
  integer, parameter, dimension(2) :: myparamarray = (/ (6), 1 /)
  integer, parameter, dimension(3) :: test = (/2, 1, (3)/)
  real(dp), intent(out) :: x

  x = myparamarray(1)+test(3)

  return
end subroutine
