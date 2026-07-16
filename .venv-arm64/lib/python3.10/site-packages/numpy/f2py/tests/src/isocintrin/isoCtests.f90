  module coddity
    use iso_c_binding, only: c_double, c_int, c_int64_t
    implicit none
    contains
      subroutine c_add(a, b, c) bind(c, name="c_add")
        real(c_double), intent(in) :: a, b
        real(c_double), intent(out) :: c
        c = a + b
      end subroutine c_add
      ! gh-9693
      function wat(x, y) result(z) bind(c)
          integer(c_int), intent(in) :: x, y
          integer(c_int) :: z

          z = x + 7
      end function wat
      ! gh-25207
      subroutine c_add_int64(a, b, c) bind(c)
        integer(c_int64_t), intent(in) :: a, b
        integer(c_int64_t), intent(out) :: c
        c = a + b
      end subroutine c_add_int64
      ! gh-25207
      subroutine add_arr(A, B, C)
         integer(c_int64_t), intent(in) :: A(3)
         integer(c_int64_t), intent(in) :: B(3)
         integer(c_int64_t), intent(out) :: C(3)
         integer :: j

         do j = 1, 3
            C(j) = A(j)+B(j)
         end do
      end subroutine
  end module coddity
