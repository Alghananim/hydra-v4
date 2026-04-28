HYDRA V4 — secrets/ directory.

Holds your local .env file. .env is gitignored.

To set up:
  1. cp .env.sample .env
  2. Fill in ANTHROPIC_API_KEY, OANDA_API_TOKEN, OANDA_ACCOUNT_ID.
  3. Source it before running:
       (Windows powershell)  Get-Content .\secrets\.env | foreach { if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path env:$($Matches[1].Trim()) -Value $Matches[2].Trim() } }
       (bash)                set -a; source secrets/.env; set +a

The framework loads them via anthropic_bridge.secret_loader.* — they
are NEVER read or printed by any other module.
