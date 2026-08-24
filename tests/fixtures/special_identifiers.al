table 70210 "Übernahme-Plan (Nord & Süd)"
{
    fields
    {
        field(1; "Externe Nr. (Alt)"; Code[20])
        {
            trigger OnValidate()
            begin
            end;
        }
        field(2; "Prüfstatus & Hinweis"; Text[50])
        {
        }
    }

    procedure "Setze Prüfstatus"(Value: Text)
    begin
    end;
}

page 70211 "Planübersicht (Täglich)"
{
    actions
    {
        area(processing)
        {
            action("Auswahl & starten (heute)")
            {
                trigger OnAction()
                begin
                    "Prüfe & Starte (Auswahl)"();
                end;
            }
            action("Auswahl & vormerken (später)")
            {
                trigger OnAction()
                begin
                end;
            }
        }
    }

    procedure "Prüfe & Starte (Auswahl)"()
    var
        "Gewählter Plan": Record "Übernahme-Plan (Nord & Süd)";
    begin
        "Gewählter Plan"."Setze Prüfstatus"('Bereit');
    end;
}
