! gh-23276
module cmplxdat
  implicit none
  integer :: i, j
  real :: x, y
  real, dimension(2) :: z
  real(kind=8) :: pi
  complex(kind=8), target :: medium_ref_index
  complex(kind=8), target :: ref_index_one, ref_index_two
  complex(kind=8), dimension(2) :: my_array
  real(kind=8), dimension(3) :: my_real_array = (/1.0d0, 2.0d0, 3.0d0/)

  data i, j / 2, 3 /
  data x, y / 1.5, 2.0 /
  data z / 3.5, 7.0 /
  data medium_ref_index / (1.d0, 0.d0) /
  data ref_index_one, ref_index_two / (13.0d0, 21.0d0), (-30.0d0, 43.0d0) /
  data my_array / (1.0d0, 2.0d0), (-3.0d0, 4.0d0) /
  data pi / 3.1415926535897932384626433832795028841971693993751058209749445923078164062d0 /
end module cmplxdat
