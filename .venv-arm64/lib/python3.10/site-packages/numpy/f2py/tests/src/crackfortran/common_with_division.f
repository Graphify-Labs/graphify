      subroutine common_with_division
      integer lmu,lb,lub,lpmin
      parameter (lmu=1)
      parameter (lb=20)
c     crackfortran fails to parse this  
c     parameter (lub=(lb-1)*lmu+1)
c     crackfortran can successfully parse this though
      parameter (lub=lb*lmu-lmu+1)
      parameter (lpmin=2)

c     crackfortran fails to parse this correctly 
c     common /mortmp/ ctmp((lub*(lub+1)*(lub+1))/lpmin+1)
      
      common /mortmp/ ctmp(lub/lpmin+1)
      
      return
      end
