import com.masque.core.MApp;
import com.masque.net.NetMsg;

interface ILoggable {
    function log():Void;
}

class BaseClient {
    public function new() {}
}

class HttpClient extends BaseClient implements ILoggable {
    private var mBaseUrl:String;

    public function new(baseUrl:String) {
        super();
        mBaseUrl = baseUrl;
    }

    public function get(path:String):String {
        return buildRequest("GET", path);
    }

    public function post(path:String, body:String):String {
        return buildRequest("POST", path);
    }

    private function buildRequest(method:String, path:String):String {
        return method + " " + mBaseUrl + path;
    }

    public function log():Void {}
}

enum CardSuit {
    SPADES;
    HEARTS;
    DIAMONDS;
    CLUBS;
}

enum abstract Rank(Int) {
    var ACE = 1;
    var KING = 13;
}

typedef Config = {
    var baseUrl:String;
    var timeout:Int;
}

function createClient(cfg:Config):HttpClient {
    return new HttpClient(cfg.baseUrl);
}
