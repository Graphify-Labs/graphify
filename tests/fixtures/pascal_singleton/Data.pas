unit Data;

interface

type
  TDM = class(TDataModule)
    procedure OpenPeriod;
    procedure Shared;
    procedure Calc(Year: Integer);
  end;

  TBase = class(TObject)
    procedure Inherited_Only;
  end;

  TDerived = class(TBase)
    procedure Own;
  end;

var
  DM: TDM = nil;
  Derived: TDerived = nil;
  Sizes: array[1..12] of TDM;

implementation

procedure TDM.OpenPeriod;
begin
end;

procedure TDM.Shared;
begin
end;

procedure TDM.Calc(Year: Integer);
begin
end;

procedure TBase.Inherited_Only;
begin
end;

procedure TDerived.Own;
begin
end;

end.
