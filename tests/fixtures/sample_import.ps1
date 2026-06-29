Import-Module Foo
Import-Module -Name Bar.psm1
. ./Shared.psm1
. .\Utils.ps1

function Invoke-Main {
    Import-Module InnerMod
    . ./InnerShared.psm1
    Get-Data
}
