unit ScopedCallsUnit;

interface

type
  TFirstWidget = class(TObject)
  public
    procedure Configure;
    procedure Reset;
  end;

  TSecondWidget = class(TObject)
  public
    procedure Configure;
    procedure Reset;
  end;

  TBaseWidget = class(TObject)
  public
    procedure Prepare;
  end;

  TDerivedWidget = class(TBaseWidget)
  public
    procedure Run;
  end;

implementation

procedure TFirstWidget.Configure;
begin
  Reset;
end;

procedure TFirstWidget.Reset;
begin
  { first reset }
end;

procedure TSecondWidget.Configure;
begin
  Reset;
end;

procedure TSecondWidget.Reset;
begin
  { second reset }
end;

procedure TBaseWidget.Prepare;
begin
  { base prepare }
end;

procedure TDerivedWidget.Run;
begin
  Prepare;
end;

end.
