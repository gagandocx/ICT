@echo off
REM ============================================================
REM  UpdateICT.bat - Auto-update and compile the ICT Trading Bot
REM  Target folder: F:\Automation\EA Testing\ICT
REM  Repository:    https://github.com/gagandocx/ICT
REM ============================================================

set "INSTALL_DIR=F:\Automation\EA Testing\ICT"
set "REPO_URL=https://github.com/gagandocx/ICT.git"
set "MT5_ADVISORS=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\C6552DBB8EB4F1A93171272A174537F8\MQL5\Experts\Advisors"
set "MQ5_SOURCE=%INSTALL_DIR%\ICT_Bot.mq5"
set "MQ5_TARGET=%MT5_ADVISORS%\ICT_Bot.mq5"

echo ============================================================
echo   ICT Trading Bot - Update and Compile Script
echo ============================================================
echo.

REM --- Check for Git ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 goto :no_git

REM --- Clone or pull the latest code ---
if exist "%INSTALL_DIR%\.git" goto :pull_repo
goto :clone_repo

:pull_repo
echo [INFO] Existing repo found. Pulling latest updates...
pushd "%INSTALL_DIR%"
git fetch origin
if %ERRORLEVEL% neq 0 goto :fetch_failed
git reset --hard origin/main
if %ERRORLEVEL% neq 0 goto :reset_failed
popd
echo [OK] Repository updated to latest version.
goto :copy_mq5

:clone_repo
echo [INFO] No existing repo found. Cloning fresh copy...
if not exist "%INSTALL_DIR%" goto :do_clone
echo [INFO] Directory exists but is not a git repository. Removing old contents...
rmdir /s /q "%INSTALL_DIR%"
if exist "%INSTALL_DIR%" goto :rmdir_failed

:do_clone
git clone "%REPO_URL%" "%INSTALL_DIR%"
if %ERRORLEVEL% neq 0 goto :clone_failed
echo [OK] Repository cloned successfully.
goto :copy_mq5

REM --- Copy ICT_Bot.mq5 to MT5 Experts\Advisors ---
:copy_mq5
echo.
if not exist "%MQ5_SOURCE%" goto :no_mq5_source
echo [INFO] Copying ICT_Bot.mq5 to MT5 Experts\Advisors...
if not exist "%MT5_ADVISORS%" mkdir "%MT5_ADVISORS%"
copy /Y "%MQ5_SOURCE%" "%MQ5_TARGET%"
if %ERRORLEVEL% neq 0 goto :copy_failed
echo [OK] ICT_Bot.mq5 copied to %MT5_ADVISORS%
goto :compile

:no_mq5_source
echo [WARNING] ICT_Bot.mq5 not found in %INSTALL_DIR%. Skipping copy.
goto :compile

REM --- Compile ICT_Bot.mq5 using MetaEditor ---
:compile
echo.
set "METAEDITOR="

set "ME_PATH1=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\C6552DBB8EB4F1A93171272A174537F8\metaeditor64.exe"
if exist "%ME_PATH1%" set "METAEDITOR=%ME_PATH1%"
if defined METAEDITOR goto :do_compile

set "ME_PATH2=C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe"
if exist "%ME_PATH2%" set "METAEDITOR=%ME_PATH2%"
if defined METAEDITOR goto :do_compile

set "ME_PATH3=C:\Program Files\MetaTrader 5\metaeditor64.exe"
if exist "%ME_PATH3%" set "METAEDITOR=%ME_PATH3%"
if defined METAEDITOR goto :do_compile

set "ME_PATH4=C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe"
if exist "%ME_PATH4%" set "METAEDITOR=%ME_PATH4%"
if defined METAEDITOR goto :do_compile

goto :no_metaeditor

:do_compile
echo [INFO] Compiling ICT_Bot.mq5 using MetaEditor...
"%METAEDITOR%" /compile:"%MQ5_TARGET%"
if %ERRORLEVEL% neq 0 goto :compile_warning
echo [OK] ICT_Bot.mq5 compiled successfully.
goto :done

:compile_warning
echo [WARNING] Compilation may have encountered errors. Check MetaEditor log.
goto :done

:no_metaeditor
echo [WARNING] MetaEditor (metaeditor64.exe) not found.
echo          Please compile ICT_Bot.mq5 manually from within MetaTrader 5.
echo          Searched:
echo            C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\C6552DBB8EB4F1A93171272A174537F8\
echo            C:\Program Files\Fusion Markets MetaTrader 5\
echo            C:\Program Files\MetaTrader 5\
echo            C:\Program Files (x86)\MetaTrader 5\
goto :done

REM --- Success ---
:done
echo.
echo ============================================================
echo   Done, Ready to trade
echo ============================================================
pause
exit /b 0

REM --- Error handlers ---
:no_git
echo [ERROR] Git is not installed or not in PATH.
echo Please install Git from https://git-scm.com/downloads
pause
exit /b 1

:fetch_failed
echo [ERROR] Git fetch failed. Check your internet connection.
popd
pause
exit /b 1

:reset_failed
echo [ERROR] Git reset failed. The repository may be corrupted.
popd
pause
exit /b 1

:rmdir_failed
echo [ERROR] Failed to remove existing directory: %INSTALL_DIR%
echo         Please close any programs using files in that folder and try again.
pause
exit /b 1

:clone_failed
echo [ERROR] Git clone failed. Check your internet connection and repo URL.
pause
exit /b 1

:copy_failed
echo [WARNING] Failed to copy ICT_Bot.mq5 to MT5 Advisors folder.
pause
exit /b 1
