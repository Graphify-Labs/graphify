module gh23879
    implicit none
    private
    public :: foo

 contains

    subroutine foo(a, b)
       integer, intent(in) :: a
       integer, intent(out) :: b
       b = a
       call bar(b)
    end subroutine

    subroutine bar(x)
        integer, intent(inout) :: x
        x = 2*x
     end subroutine

 end module gh23879
