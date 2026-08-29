namespace Example.App;

using Example.Shared;

interface "IWorker"
{
    procedure Run(Target: Record "Work Item"): Boolean;
}

enum 75100 "Work Kind" implements "IWorker"
{
    value(0; Standard)
    {
        Implementation = "IWorker" = "Worker Impl";
    }
}

enumextension 75101 "More Work Kinds" extends "Work Kind" { }

table 75102 "Work Item"
{
    fields
    {
        field(1; "Entry No."; Integer)
        {
            trigger OnValidate()
            begin
            end;
        }
        field(2; Description; Text[100])
        {
            trigger OnValidate()
            begin
            end;
        }
    }
}

tableextension 75103 "Work Item Ext" extends "Work Item" { }
page 75104 "Work Items" { }
pageextension 75105 "Work Items Ext" extends "Work Items" { }
report 75106 "Work Report" { }
reportextension 75107 "Work Report Ext" extends "Work Report" { }
query 75108 "Work Query" { }
xmlport 75109 "Work Export" { }
permissionset 75112 "Work Permissions"
{
    Assignable = true;
    Permissions = tabledata "Work Item" = R;
}
permissionsetextension 75113 "Extra Work Permissions" extends "Work Permissions" { }

codeunit 75110 "Worker Impl" implements "IWorker"
{
    [IntegrationEvent(false, false)]
    local procedure OnWorked()
    begin
    end;

    procedure Run(Target: Record "Work Item"): Boolean
    var
        OtherWorker: Codeunit "Worker Impl";
    begin
        OtherWorker.OnWorked();
        exit(true);
    end;
}

codeunit 75111 "Worker Subscriber"
{
    [EventSubscriber(ObjectType::Codeunit, Codeunit::"Worker Impl", 'OnWorked', '', false, false)]
    local procedure HandleWorked()
    begin
    end;
}