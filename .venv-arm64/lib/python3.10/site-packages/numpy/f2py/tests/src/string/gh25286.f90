subroutine charint(trans, info)
    character, intent(in) :: trans
    integer, intent(out) :: info
    if (trans == 'N') then
        info = 1
    else if (trans == 'T') then
        info = 2
    else if (trans == 'C') then
        info = 3
    else
        info = -1
    end if

end subroutine charint
