function RunBot
{
    conda activate reddit-function-bot
    func start --functions function-timer-submit-post function-queue-submission-worker --verbose --port 8008
}

while(1) {
    RunBot
}