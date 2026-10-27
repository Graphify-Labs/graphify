classdef C < pkg.Base & handle
    methods (Abstract)
        y = declared(obj, x)
    end
    methods
        function y = run(obj, x)
            y = nested(x);
            function z = nested(v)
                z = v;
            end
        end
    end
end

function helper()
end
