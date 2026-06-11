trigger AccountTrigger on Account (before insert, before update, after insert, after update) {
    if (Trigger.isBefore) {
        AccountService.validateAccounts(Trigger.new);
    }
    if (Trigger.isAfter && Trigger.isInsert) {
        AccountService.sendWelcomeNotifications(Trigger.new);
    }
}
