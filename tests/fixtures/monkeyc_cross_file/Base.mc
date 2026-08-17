// Base module + base view, extended and called from App.mc.
using Toybox.WatchUi as Ui;
import Toybox.Lang;

module Store {
    var _cache as Dictionary = {};

    function get(key as Symbol) as Number or Null {
        return _cache.get(key);
    }

    function put(key as Symbol, value as Number) as Void {
        _cache.put(key, value);
    }
}

class BaseView extends Ui.View {
    function initialize() {
        View.initialize();
    }

    function refresh() as Void {
        Store.put(:refreshed, 1);
    }
}
