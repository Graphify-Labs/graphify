// Derived view: extends a class from Base.mc, calls its module and inherits its method.
using Toybox.WatchUi as Ui;
import Toybox.Lang;
import Store;

class MainView extends BaseView {
    private var _other as BaseView;

    function initialize() {
        BaseView.initialize();      // superclass call across files
        _other = new BaseView();    // constructor call across files
    }

    function onShow() as Void {
        var n = Store.get(:count);  // Module.fn() across files
        refresh();                  // inherited from BaseView (other file)
        _other.refresh();           // typed receiver across files
        Store.reset();              // Store has no reset(): type-level `references` edge
    }
}
