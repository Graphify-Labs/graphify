unit Guarded;

interface

type
  TGuarded = class
    procedure WithGuardedLocals;
    function AfterTheDirective: Integer;
  end;

implementation

procedure TGuarded.WithGuardedLocals;
{$IFDEF SOME_BUILD}
var
  Scratch: Integer;
{$ENDIF}
begin
{$IFDEF SOME_BUILD}
  Scratch := 1;
{$ENDIF}
end;

function TGuarded.AfterTheDirective: Integer;
begin
  Result := 2;
end;

end.
