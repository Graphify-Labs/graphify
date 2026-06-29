@{
    RootModule        = 'MyModule.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = 'aaaabbbb-cccc-dddd-eeee-ffffffffffff'
    Author            = 'Test Author'
    Description       = 'A sample module manifest for graphify tests.'
    NestedModules     = @('Helpers.psm1', 'Logger.psm1')
    RequiredModules   = @(
        'PSReadLine',
        @{ ModuleName = 'Pester'; ModuleVersion = '5.0' }
    )
    FunctionsToExport = @('Get-Data', 'Process-Items')
}
