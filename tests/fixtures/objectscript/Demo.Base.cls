/// Base class
Class Demo.Base Extends %RegisteredObject
{

Property Name As %String;

Property Tags As List Of %String;

Property Util As Demo.Util;

Method Start() As %Status
{
    Set ..Name = "base"
    Quit $$$OK
}

}
