unit RecordMethodsUnit;

interface

type
  TVec = record
    X, Y: Integer;
    function Len: Integer;
    class operator Add(a, b: TVec): TVec;
  end;

implementation

function TVec.Len: Integer;
begin
  Result := 0;
end;

class operator TVec.Add(a, b: TVec): TVec;
begin
  Result.X := a.X + b.X;
  Result.Y := a.Y + b.Y;
end;

end.
