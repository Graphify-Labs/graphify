unit Caller;

interface

uses Data;

type
  TCallerForm = class(TForm)
    Query: TDM;
    procedure Run;
    procedure Shared;
  end;

var
  Query: TDM = nil;

implementation

procedure TCallerForm.Run;
var
  Local: TDM;
begin
  DM.OpenPeriod;
  DM.Calc(2026);
  DM.Shared;
  Derived.Inherited_Only;
  Query.OpenPeriod;
  Local.OpenPeriod;
  Sizes.OpenPeriod;
  Self.Shared;
end;

procedure TCallerForm.Shared;
begin
end;

end.
