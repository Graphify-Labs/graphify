      SUBROUTINE TESTSUB(
     &    INPUT1, INPUT2,                                 !Input
     &    OUTPUT1, OUTPUT2)                               !Output

      IMPLICIT NONE
      INTEGER, INTENT(IN) :: INPUT1, INPUT2
      INTEGER, INTENT(OUT) :: OUTPUT1, OUTPUT2

      OUTPUT1 = INPUT1 + INPUT2
      OUTPUT2 = INPUT1 * INPUT2

      RETURN
      END SUBROUTINE TESTSUB

      SUBROUTINE TESTSUB2(OUTPUT)
      IMPLICIT NONE
      INTEGER, PARAMETER :: N = 10 ! Array dimension
      REAL, INTENT(OUT) :: OUTPUT(N)
      INTEGER :: I

      DO I = 1, N
         OUTPUT(I) = I * 2.0
      END DO

      RETURN
      END
