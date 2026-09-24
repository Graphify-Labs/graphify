unit OtherModule;

interface

type
  TOtherModule = class
  public
    procedure ServerReport(const Msg: string);
    procedure Flush;
  end;

var
  om: TOtherModule;

implementation

procedure TOtherModule.ServerReport(const Msg: string);
begin
end;

procedure TOtherModule.Flush;
begin
end;

end.
