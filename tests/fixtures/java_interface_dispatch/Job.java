public class Job {
    private final Worker worker;

    public Job(Worker worker) {
        this.worker = worker;
    }

    public void execute() {
        this.worker.run();
    }
}
