unit MainModule;

interface

type
  TMainModule = class
  public
    procedure ServerReport(const Msg: string);
    function Ping: Boolean;
  end;

var
  mm: TMainModule;
  Counter, Total: Integer;

implementation

procedure TMainModule.ServerReport(const Msg: string);
begin
  Ping;
end;

function TMainModule.Ping: Boolean;
begin
  Result := True;
end;

end.
