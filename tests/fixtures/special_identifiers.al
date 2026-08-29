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
            group("Tägliche Auswahl")
            {
                action("Auswahl & starten")
                {
                    trigger OnAction()
                    begin
                        "Prüfe & Starte (Auswahl)"();
                    end;
                }
            }
            group("Spätere Auswahl")
            {
                action("Auswahl & starten")
                {
                    trigger OnAction()
                    begin
                    end;
                }
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

report 70212 "Prüfliste (Regionen)"
{
    dataset
    {
        dataitem("Nördliche Auswahl"; Customer)
        {
            trigger OnAfterGetRecord()
            begin
                "Sammle Ergebnis"();
            end;
        }
        dataitem("Südliche Auswahl"; Vendor)
        {
            trigger OnAfterGetRecord()
            begin
                "Sammle Ergebnis"();
            end;
        }
    }

    procedure "Sammle Ergebnis"()
    begin
    end;
}
