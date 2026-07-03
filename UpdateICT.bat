@echo off
REM ============================================================
REM  UpdateICT.bat - Auto-update and run the ICT Trading Bot
REM  Target folder: F:\Automation\EA Testing\ICT
REM  Repository:    https://github.com/gagandocx/ICT
REM ============================================================

setlocal enabledelayedexpansion

set "INSTALL_DIR=F:\Automation\EA Testing\ICT"
set "REPO_URL=https://github.com/gagandocx/ICT.git"
set "PYTHON=python"

echo ============================================================
echo   ICT Trading Bot - Update and Run Script
echo ============================================================
echo.

REM --- Check for Git ---
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Git is not installed or not in PATH.
    echo Please install Git from https://git-scm.com/downloads
    pause
    exit /b 1
)

REM --- Check for Python ---
where %PYTHON% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- Clone or pull the latest code ---
if exist "%INSTALL_DIR%\.git" (
    echo [INFO] Existing repo found. Pulling latest updates...
    pushd "%INSTALL_DIR%"
    git fetch origin
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Git fetch failed. Check your internet connection.
        popd
        pause
        exit /b 1
    )
    git reset --hard origin/main
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Git reset failed. The repository may be corrupted.
        popd
        pause
        exit /b 1
    )
    git clean -fd
    popd
    echo [OK] Repository updated to latest version.
) else (
    echo [INFO] No existing repo found. Cloning fresh copy...
    REM If directory exists but is not a git repo, remove it entirely first
    if exist "%INSTALL_DIR%" (
        echo [INFO] Directory exists but is not a git repository. Removing old contents...
        rmdir /s /q "%INSTALL_DIR%"
        if exist "%INSTALL_DIR%" (
            echo [ERROR] Failed to remove existing directory: %INSTALL_DIR%
            echo         Please close any programs using files in that folder and try again.
            pause
            exit /b 1
        )
    )
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Git clone failed. Check your internet connection and repo URL.
        pause
        exit /b 1
    )
    echo [OK] Repository cloned successfully.
)

echo.

REM --- Verify critical files exist after clone/pull ---
if not exist "%INSTALL_DIR%\main.py" (
    echo [ERROR] main.py not found in %INSTALL_DIR%
    echo         The clone or pull may have failed silently. Try deleting the folder and running again.
    pause
    exit /b 1
)
if not exist "%INSTALL_DIR%\requirements.txt" (
    echo [ERROR] requirements.txt not found in %INSTALL_DIR%
    echo         The clone or pull may have failed silently. Try deleting the folder and running again.
    pause
    exit /b 1
)

REM --- Install/Update Python dependencies ---
echo [INFO] Installing/updating Python dependencies...
pushd "%INSTALL_DIR%"
%PYTHON% -m pip install --upgrade pip >nul 2>&1
%PYTHON% -m pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo [WARNING] Some dependencies may have failed to install.
    echo          MetaTrader5 package requires Windows with MT5 terminal installed.
    echo          Other packages should install normally.
)
popd
echo [OK] Dependencies processed.
echo.

REM --- Check for config file ---
if not exist "%INSTALL_DIR%\config\settings.yaml" (
    if exist "%INSTALL_DIR%\config\config_example.yaml" (
        echo [INFO] No settings.yaml found. Copying example config...
        copy "%INSTALL_DIR%\config\config_example.yaml" "%INSTALL_DIR%\config\settings.yaml"
        echo [WARNING] Please edit config\settings.yaml with your MT5 and Telegram credentials.
        echo          Opening config file for editing...
        notepad "%INSTALL_DIR%\config\settings.yaml"
    )
)

REM --- Copy ICT_Bot.mq5 to MT5 Experts\Advisors ---
set "MT5_ADVISORS=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\C6552DBB8EB4F1A93171272A174537F8\MQL5\Experts\Advisors"
set "MQ5_SOURCE=%INSTALL_DIR%\ICT_Bot.mq5"

if exist "%MQ5_SOURCE%" (
    echo [INFO] Copying ICT_Bot.mq5 to MT5 Experts\Advisors...
    if not exist "%MT5_ADVISORS%" (
        mkdir "%MT5_ADVISORS%"
    )
    copy /Y "%MQ5_SOURCE%" "%MT5_ADVISORS%\ICT_Bot.mq5"
    if !ERRORLEVEL! neq 0 (
        echo [WARNING] Failed to copy ICT_Bot.mq5 to MT5 Advisors folder.
    ) else (
        echo [OK] ICT_Bot.mq5 copied to %MT5_ADVISORS%
    )
) else (
    echo [WARNING] ICT_Bot.mq5 not found in %INSTALL_DIR%. Skipping copy.
)
echo.

REM --- Compile ICT_Bot.mq5 using MetaEditor ---
set "METAEDITOR="
set "MQ5_TARGET=%MT5_ADVISORS%\ICT_Bot.mq5"

REM Try common MetaEditor locations
if exist "C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe" (
    set "METAEDITOR=C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe"
) else if exist "C:\Program Files\MetaTrader 5\metaeditor64.exe" (
    set "METAEDITOR=C:\Program Files\MetaTrader 5\metaeditor64.exe"
) else if exist "C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe" (
    set "METAEDITOR=C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe"
)

if defined METAEDITOR (
    echo [INFO] Compiling ICT_Bot.mq5 using MetaEditor...
    "%METAEDITOR%" /compile:"%MQ5_TARGET%"
    if !ERRORLEVEL! neq 0 (
        echo [WARNING] Compilation may have encountered errors. Check MetaEditor log.
    ) else (
        echo [OK] ICT_Bot.mq5 compiled successfully.
    )
) else (
    echo [WARNING] MetaEditor (metaeditor64.exe) not found in common locations.
    echo          Please compile ICT_Bot.mq5 manually from within MetaTrader 5.
    echo          Searched: C:\Program Files\Fusion Markets MetaTrader 5\
    echo                    C:\Program Files\MetaTrader 5\
    echo                    C:\Program Files (x86)\MetaTrader 5\
)
echo.

REM --- Run the bot ---
echo ============================================================
echo   Starting ICT Trading Bot...
echo ============================================================
echo.
pushd "%INSTALL_DIR%"
%PYTHON% main.py live
popd

echo.
echo Done, Ready to trade
pause
