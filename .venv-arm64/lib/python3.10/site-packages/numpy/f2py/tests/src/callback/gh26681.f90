module utils
    implicit none
  contains
    subroutine my_abort(message)
      implicit none
      character(len=*), intent(in) :: message
      !f2py callstatement PyErr_SetString(PyExc_ValueError, message);f2py_success = 0;
      !f2py callprotoargument char*
      write(0,*) "THIS SHOULD NOT APPEAR"
      stop 1
    end subroutine my_abort

    subroutine do_something(message)
        !f2py    intent(callback, hide) mypy_abort
        character(len=*), intent(in) :: message
        call mypy_abort(message)
    end subroutine do_something
end module utils
