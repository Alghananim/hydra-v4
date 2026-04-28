@echo off
chcp 65001 >nul
title HYDRA V4 - Phase 2 Verify (imports + tests)
color 0B

cls
echo.
echo  ============================================================
echo            HYDRA V4 - PHASE 2 VERIFY
echo  ============================================================
echo.
echo  Steps:
echo    1. Verify 5 brains + Orchestrator + Replay can be imported
echo    2. Run pytest on full tree, capture pass/fail count
echo.
echo  Output: %USERPROFILE%\Desktop\PHASE2_VERIFY.txt
echo.
echo  Press any key to start.
pause >nul

set "ROOT=%USERPROFILE%\Desktop\HYDRA V4"
set "OUT=%USERPROFILE%\Desktop\PHASE2_VERIFY.txt"

cd /d "%ROOT%"

echo HYDRA V4 - PHASE 2 VERIFY > "%OUT%"
echo Started: %DATE% %TIME% >> "%OUT%"
echo Working dir: %CD% >> "%OUT%"
echo. >> "%OUT%"

echo === [1] FIVE BRAINS + ORCHESTRATOR IMPORT CHECK === >> "%OUT%"
python -c "import sys; sys.path.insert(0, '.'); from newsmind.v4.NewsMindV4 import NewsMindV4; print('  newsmind: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from marketmind.v4.MarketMindV4 import MarketMindV4; print('  marketmind: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from chartmind.v4.ChartMindV4 import ChartMindV4; print('  chartmind: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from gatemind.v4.GateMindV4 import GateMindV4; print('  gatemind: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4; print('  smartnotebook: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4; print('  orchestrator: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from replay.replay_calendar import build_replay_occurrences; print('  replay_calendar: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from replay.replay_newsmind import ReplayNewsMindV4; print('  replay_newsmind: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from replay.two_year_replay import TwoYearReplay; print('  two_year_replay: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from replay.leakage_guard import _bar_time, slice_visible; print('  leakage_guard: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from anthropic_bridge.bridge import AnthropicBridge; print('  anthropic_bridge: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from live_data.oanda_readonly_client import OandaReadOnlyClient; print('  oanda_readonly_client: OK')" >> "%OUT%" 2>&1
python -c "import sys; sys.path.insert(0, '.'); from live_data.live_order_guard import assert_no_live_order; print('  live_order_guard: OK')" >> "%OUT%" 2>&1

echo. >> "%OUT%"

echo === [2] PYTEST FULL TREE === >> "%OUT%"
python -m pytest --tb=short -q 2>&1 | findstr /v /c:"^$" >> "%OUT%"

echo. >> "%OUT%"
echo === [3] PYTEST SUMMARY === >> "%OUT%"
python -m pytest --tb=no -q 2>&1 | findstr /R "passed failed error" >> "%OUT%"

echo. >> "%OUT%"
echo Finished: %DATE% %TIME% >> "%OUT%"

echo.
echo  ============================================================
echo  Verify complete. See: %OUT%
echo  ============================================================
echo.
echo  Press any key to close.
pause >nul
exit /b 0
