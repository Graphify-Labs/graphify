subroutine shift_a(dim_a, a)
    use data, only: shift
    integer, intent(in) :: dim_a
    real(8), intent(inout), dimension(dim_a) :: a
    a = a + shift
end subroutine shift_a
