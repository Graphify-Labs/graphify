using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Demo.ViewModels;

public partial class ToolkitViewModel : ObservableObject
{
    [ObservableProperty]
    private string userName = "";

    [ObservableProperty] private string email = "";

    // ObservableProperty
    private string ignoredName = "";

    [RelayCommand]
    private async Task SaveAsync()
    {
        await Task.CompletedTask;
    }

    [RelayCommand] private void Refresh()
    {
    }

    // RelayCommand
    private void Ignored()
    {
    }
}
