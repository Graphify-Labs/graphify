// `Twin.ping()` is ambiguous across A.mc / B.mc -> no edge (god-node guard).
class Caller {
    function go() as Void {
        Twin.ping();
    }
}
