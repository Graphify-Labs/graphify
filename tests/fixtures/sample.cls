public with sharing class AccountService {

    private static final String DEFAULT_TYPE = 'Customer';

    public interface Notifiable {
        void notify(String message);
    }

    public enum AccountStatus { ACTIVE, INACTIVE, PENDING }

    @AuraEnabled
    public static List<Account> getAccounts(String accountType) {
        return [SELECT Id, Name, Type FROM Account WHERE Type = :accountType];
    }

    @future
    public static void updateAccountsAsync(List<Id> accountIds) {
        List<Account> accounts = [SELECT Id FROM Account WHERE Id IN :accountIds];
        for (Account acc : accounts) {
            acc.Type = DEFAULT_TYPE;
        }
        update accounts;
    }

    @InvocableMethod(label='Create Account' description='Creates a new Account')
    public static List<Id> createAccounts(List<String> names) {
        List<Account> toInsert = new List<Account>();
        for (String n : names) {
            toInsert.add(new Account(Name = n));
        }
        insert toInsert;
        List<Id> ids = new List<Id>();
        for (Account a : toInsert) {
            ids.add(a.Id);
        }
        return ids;
    }

    public static void deleteOldAccounts(Date cutoff) {
        List<Account> old = [SELECT Id FROM Account WHERE CreatedDate < :cutoff];
        delete old;
    }

    @isTest
    static void testGetAccounts() {
        List<Account> result = getAccounts('Customer');
        System.assertNotEquals(null, result);
    }

    @isTest
    static void testCreateAccounts() {
        List<Id> ids = createAccounts(new List<String>{'Test'});
        System.assertEquals(1, ids.size());
    }
}
