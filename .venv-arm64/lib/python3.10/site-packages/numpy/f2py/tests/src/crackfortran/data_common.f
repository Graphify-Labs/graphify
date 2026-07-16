        BLOCK DATA PARAM_INI
        COMMON /MYCOM/ MYDATA
            DATA MYDATA /0/
        END
        SUBROUTINE SUB1
        COMMON /MYCOM/ MYDATA
        MYDATA = MYDATA + 1
        END
