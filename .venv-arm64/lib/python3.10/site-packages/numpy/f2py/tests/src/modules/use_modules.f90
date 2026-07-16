module mathops
  implicit none
contains
  function add(a, b) result(c)
    integer, intent(in) :: a, b
    integer :: c
    c = a + b
  end function add
end module mathops

module useops
  use mathops, only: add
  implicit none
contains
  function sum_and_double(a, b) result(d)
    integer, intent(in) :: a, b
    integer :: d
    d = 2 * add(a, b)
  end function sum_and_double
end module useops
