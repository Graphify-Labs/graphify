unit Stranger;

interface

type
  TStranger = class(TObject)
    procedure Run;
  end;

implementation

procedure TStranger.Run;
begin
  DM.OpenPeriod;
end;

end.
