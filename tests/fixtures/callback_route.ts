function sendReply(name: string): void {
    console.log(`Hello, ${name}`);
}

function logMessage(msg: string): void {
    console.log(msg);
}

const app = route();

app.get('/welcome', (req: Request, res: Response) => {
    sendReply('visitor');
    res.json({ ok: true });
});

app.use('/health', (req: Request, res: Response) => {
    logMessage('health check');
    res.json({ ok: true });
});
