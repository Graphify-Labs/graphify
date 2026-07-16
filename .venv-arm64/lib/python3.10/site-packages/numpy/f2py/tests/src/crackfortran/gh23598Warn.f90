module test_bug
    implicit none
    private
    public :: intproduct

contains
    integer function intproduct(a, b) result(res)
    integer, intent(in) :: a, b
    res = a*b
    end function
end module
