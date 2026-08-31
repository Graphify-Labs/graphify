unit DerivedGadget;

interface

uses
  BaseGadget;

type
  TDerivedGadget = class(TBaseGadget)
  public
    procedure Run;
  end;

implementation

procedure TDerivedGadget.Run;
begin
  Prepare;
end;

end.
