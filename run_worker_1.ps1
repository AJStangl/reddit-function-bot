function RunBot
{
    conda activate reddit-function-bot
    func start --functions function-timer-text-generation-worker-1  --port 7091
}

while(1) {
    RunBot
}
