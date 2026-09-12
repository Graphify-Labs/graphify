// Apex allows class modifiers in any order, and any number of them. Every
// declaration below must produce a node; `BaseBuilder`, `Runnable` and
// `Account` are only referenced here, so they must stay sourceless.
public abstract with sharing class ReportBuilder extends BaseBuilder implements Runnable {

    global without sharing virtual class Nested {
    }

    public with sharing class Legacy {
    }

    private static final class Constants {
    }

    public override void build() {
        List<Account> rows = [SELECT Id, Name FROM Account];
    }
}
