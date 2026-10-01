unit Form1;

interface

uses
  MainModule, OtherModule;

type
  TForm1 = class
  public
    procedure ButtonClick;
    procedure Local;
  end;

implementation

procedure TForm1.Local;
begin
end;

procedure TForm1.ButtonClick;
begin
  mm.ServerReport('clicked');
  om.Flush;
  Self.Local;
  Orphan;
end;

end.
