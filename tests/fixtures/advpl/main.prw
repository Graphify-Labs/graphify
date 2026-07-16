#include "COMMON.CH"

/*/{Protheus.doc} StartProcess
Synthetic entry point used by Graphify tests.
@type user function
@example FakeFromDocumentation()
/*/
User Function StartProcess()
    Local cText := "FakeFromString() // not a comment"
    Local nValue := U_PublicHelper()
    Local nOther := LocalHelper()
Return nValue + nOther

Static Function LocalHelper()
Return 1

Function ProductFunction()
Return PublicHelper()
