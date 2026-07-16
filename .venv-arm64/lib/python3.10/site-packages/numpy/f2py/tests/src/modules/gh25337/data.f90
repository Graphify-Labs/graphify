module data
   real(8) :: shift
contains
   subroutine set_shift(in_shift)
      real(8), intent(in) :: in_shift
      shift = in_shift
   end subroutine set_shift
end module data
