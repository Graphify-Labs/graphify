    module mod2
        implicit none
        PUBLIC :: mod2_func1
    contains

        subroutine mod2_func1()
            print*, "mod2_func1"
        end subroutine mod2_func1

    end module mod2

    module mod1
        implicit none
        PUBLIC :: mod1_func1
    contains

        subroutine mod1_func1()
            print*, "mod1_func1"
        end subroutine mod1_func1

    end module mod1
