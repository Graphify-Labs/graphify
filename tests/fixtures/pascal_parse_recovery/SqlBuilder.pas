unit SqlBuilder;

interface

type
  TSqlBuilder = class
    function QuotedLookup(const Name: string): string;
    function AfterTheQuotedLiteral: Integer;
  end;

implementation

function TSqlBuilder.QuotedLookup(const Name: string): string;
begin
  // A literal whose first content character is an escaped apostrophe.
  // tree-sitter-pascal mis-lexes this and drops the rest of the unit.
  Result := 'select db_id('''+Name+''') as dbname';
end;

function TSqlBuilder.AfterTheQuotedLiteral: Integer;
begin
  Result := 1;
end;

end.
