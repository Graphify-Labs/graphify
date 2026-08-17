// Sample Monkey C (Garmin Connect IQ) source for the extractor tests.
/* A block comment with a stray brace { and a fake declaration:
   function nope() { }
   class Nope { }
*/
using Toybox.WatchUi as Ui;
using Toybox.Graphics;
import Toybox.Lang;
import Toybox.Timer;
import Toybox.System;
import Helpers;

const GREETING = "hello { world // not a comment";

enum { STATE_IDLE, STATE_BUSY }

module Helpers {
    var _counter as Number = 0;

    function bump(step as Number) as Number {
        _counter += step;
        return _counter;
    }

    function label(prefix as String) as String {
        // bare call inside the module -> Helpers.bump
        return prefix + " " + bump(1).toString();
    }

    class Ticker {
        hidden var _timer as Timer.Timer or Null;
        private var _ticks as Number = 0;

        function initialize() {
            _timer = new Timer.Timer();
        }

        function start() as Void {
            // callback registered by symbol -> .onTick()
            _timer.start(method(:onTick), 1000, true);
            // the older Method-object form -> .onIdle()
            var idle = new Lang.Method(self, :onIdle);
            if (idle == null) { throw new Lang.InvalidValueException("no callback"); }
        }

        function onIdle() as Void {
            _ticks = 0;
        }

        function onTick() as Void {
            _ticks = _ticks + 1;
            me.report();          // me. -> own method
            Helpers.bump(2);      // Module.fn() -> raw member call, static receiver
        }

        function report() as Void {
            System.println(label("ticks"));   // bare -> enclosing module Helpers.label
            var again = me.method(:onIdle);   // receiver form of the callback shorthand
        }
    }
}

class SampleView extends Ui.View {
    private var _ticker as Helpers.Ticker;
    private var _delegate;

    function initialize() {
        View.initialize();
        _ticker = new Helpers.Ticker();
        _delegate = new SampleDelegate();    // local class -> calls edge
    }

    function onShow() as Void {
        _ticker.start();                     // typed field -> raw member call, typed receiver
        $.Helpers.bump(3);                   // global-scope qualifier is dropped -> Helpers.bump()
        var s = new SampleDelegate();
        s.onBack();                          // local typed via `new` -> raw member call
        requestUpdate();                     // inherited SDK method -> raw bare call
    }

    (:debug) private function _dump(dc as Graphics.Dc) as Void {
        dc.drawText(0, 0, Graphics.FONT_SMALL, GREETING, Graphics.TEXT_JUSTIFY_LEFT);
        var d = { :title => "x", :count => 3 };
        if (d.hasKey(:title)) { System.println('{'); }
        switch (_delegate) {
            case null: { break; }
            default: { break; }
        }
    }
}

class SampleDelegate extends Ui.BehaviorDelegate {
    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onBack() as Boolean {
        Ui.popView(Ui.SLIDE_DOWN);
        return true;
    }
}

class DerivedView extends SampleView {
    function initialize() {
        SampleView.initialize();   // superclass call, local static receiver
    }

    function onHide() as Void {
        onShow();                  // inherited from SampleView -> raw bare call (self_scope)
    }
}
