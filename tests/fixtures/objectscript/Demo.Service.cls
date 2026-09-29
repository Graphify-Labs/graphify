Include DemoMacros
Class Demo.Service Extends Demo.Base
{
Parameter ADAPTER = "Demo.Util";
ClassMethod Run() As %Status
{
    Set util = ##class(Demo.Util).%New()
    Do ##class(Demo.Base).Start()
    Do ..Helper()
    Do ..Start()
    Set x = $$Calc^DemoLib(2)
    Quit $$$DEMOOK
}
ClassMethod Helper() {
    Quit
}
XData Config [ MimeType = "text/xml" ] {
<transform sourceClass="Demo.Base" targetClass="Demo.DT.Map"><item ClassName="Demo.Util"/></transform>
}
}
