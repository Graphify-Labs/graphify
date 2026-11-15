object ChildForm: TChildForm
  Caption = 'Child'
  inherited InheritedPanel: TPanel
    Left = 0
    OnClick = InheritedPanelClick
  end
  inline FrameHost: TFrameWidget
    Top = 10
  end
  object NativePanel: TPanel
    Top = 20
  end
end
