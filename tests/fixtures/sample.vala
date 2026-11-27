using GLib;

namespace GraphifyDemo {
    public interface IProcessor : Object {
        public abstract string process (string item);
    }

    public class Processor : Object, IProcessor {
        public string process (string item) {
            return item.up ();
        }
    }
}
