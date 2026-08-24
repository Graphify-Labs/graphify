namespace Acme.Comments;

using Acme.Shared;

table 75000 "Comment Entry"
{
    trigger OnInsert()
    begin
        Initialize();
    end;

    [IntegrationEvent(false, false)]
    local procedure Initialize(): Boolean
    begin
        // Braces in comments must not terminate the object: }
        exit('{ready}');
    end;
}

#if TEST
tableextension 75001 "Customer Comments" extends Customer
{
    procedure AddComment(CommentText: Text)
    begin
    end;
}
#endif