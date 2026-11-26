function entry()
    local();
    function local()
        sibling();
    end
    function sibling()
        local();
    end
end

function public()
    local();
end

function local()
end
