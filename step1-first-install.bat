@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

if /I "%~1"=="__run" goto :__main
cmd /v:on /c ""%~f0" __run"
set "SCRIPT_EXIT=%ERRORLEVEL%"
if not "%SCRIPT_EXIT%"=="0" (
    echo.
    echo [ERROR] Installer stopped, exit code: %SCRIPT_EXIT%
    echo Check the error messages above and try again
    echo.
    pause
)
exit /b %SCRIPT_EXIT%

:__main

REM Set PYTHONUTF8=1 to avoid conda encoding errors
set "PYTHONUTF8=1"

REM Fix %CD% becoming System32 when run as administrator
REM Use the script directory as the working directory
cd /d "%~dp0"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Only run in a git repo, a local dependency folder, or an empty folder
set "DIR_SAFE=0"
set "DIR_SAFE_REASON="
if exist "%SCRIPT_DIR%\.git" (
    set "DIR_SAFE=1"
    set "DIR_SAFE_REASON=Found .git in this folder"
) else if exist "%SCRIPT_DIR%\PortableGit\cmd\git.exe" (
    set "DIR_SAFE=1"
    set "DIR_SAFE_REASON=Found PortableGit in this folder"
) else if exist "%SCRIPT_DIR%\Miniconda3\Scripts\conda.exe" (
    set "DIR_SAFE=1"
    set "DIR_SAFE_REASON=Found Miniconda3 in this folder"
) else (
    set "DIR_HAS_OTHER_CONTENT=0"
    for /f "delims=" %%i in ('dir /a /b "%SCRIPT_DIR%" 2^>nul') do (
        if /i not "%%~nxi"=="%~nx0" (
            set "DIR_HAS_OTHER_CONTENT=1"
        )
    )
    if "!DIR_HAS_OTHER_CONTENT!"=="0" (
        set "DIR_SAFE=1"
        set "DIR_SAFE_REASON=Empty folder (installer script only)"
    )
)

if not "!DIR_SAFE!"=="1" (
    echo.
    echo [ERROR] This folder is not valid for first-time install
    echo [INFO] This folder is not empty. Put the installer in an empty folder
    echo.
    echo Current folder: %SCRIPT_DIR%
    echo.
    echo Stopped to avoid overwriting unrelated files.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Manga Translator - First-time installer
echo Manga Translator UI - Installer
echo ========================================
echo.
echo [INFO] Folder check passed: !DIR_SAFE_REASON!
echo.
echo This script will:
echo [1] Install Miniconda (Python environment, if needed)
echo [2] Download portable Git (if needed)
echo [3] Clone the repository
echo [4] Create a Python environment and install dependencies
echo [5] Finish
echo.
pause

REM ===== Step 1: Check / install Miniconda =====
echo.
echo [1/5] Checking Miniconda...
echo ========================================

REM Default install path (does not mean Conda was found)
set "MINICONDA_ROOT="
set "DEFAULT_MINICONDA_ROOT=%SCRIPT_DIR%\Miniconda3"
set "ALT_MINICONDA_ROOT=%~d0\Miniconda3"
set "CONDA_REGISTRY_FOUND=0"
set "CONDA_VALID=0"
set CONDA_INSTALLED=0
set PATH_HAS_CHINESE=0
set ALT_INSTALL_PATH=

REM Detect non-ASCII characters in the path
REM Use PowerShell for a more reliable check
set "TEMP_CHECK_PATH=%SCRIPT_DIR%"
powershell -Command "$path = '%TEMP_CHECK_PATH%'; if ($path -match '[^\x00-\x7F]') { exit 1 } else { exit 0 }" >nul 2>&1
if errorlevel 1 (
    REM Path has non-ASCII characters; use the drive root
    set "DEFAULT_MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
    set PATH_HAS_CHINESE=1
)

call :detect_conda_registry

REM Check for an existing system Conda first
if defined CONDA_EXE (
    for /f "delims=" %%i in ('"%CONDA_EXE%" info --base 2^>nul') do (
        if exist "%%i\Scripts\conda.exe" (
            set "MINICONDA_ROOT=%%i"
        )
    )
)

if not defined MINICONDA_ROOT (
    for /f "delims=" %%i in ('conda info --base 2^>nul') do (
        if exist "%%i\Scripts\conda.exe" (
            set "MINICONDA_ROOT=%%i"
        )
    )
)

if not defined MINICONDA_ROOT (
    for /f "delims=" %%i in ('where conda 2^>nul') do (
        if not defined MINICONDA_ROOT (
            if /I "%%~nxi"=="conda.exe" (
                for %%p in ("%%~dpi..") do if exist "%%~fp\Scripts\conda.exe" set "MINICONDA_ROOT=%%~fp"
            ) else if /I "%%~nxi"=="conda.bat" (
                for %%p in ("%%~dpi..") do if exist "%%~fp\Scripts\conda.exe" set "MINICONDA_ROOT=%%~fp"
            )
        )
    )
)

if defined MINICONDA_ROOT (
    call :report_conda_registry_status
    call :validate_conda_root
    if "!CONDA_VALID!"=="1" goto :found_system_conda
    echo [WARNING] Conda found but validation failed: !MINICONDA_ROOT!
    set "MINICONDA_ROOT="
)
goto :check_local_conda

:found_system_conda
echo [OK] System Conda found
echo.
echo Location: !MINICONDA_ROOT!
echo [OK] Conda validation passed
if exist "!MINICONDA_ROOT!\condabin\conda.bat" (
    set "PATH=!MINICONDA_ROOT!\condabin;!MINICONDA_ROOT!\Scripts;%PATH%"
)
if exist "!MINICONDA_ROOT!\Scripts\conda.exe" (
    call "!MINICONDA_ROOT!\Scripts\conda.exe" --version 2>nul
) else (
    call conda --version 2>nul
)
if !ERRORLEVEL! neq 0 (
    echo [WARNING] Could not read the Conda version
)

echo.
pause

goto :check_git

:check_local_conda
REM Check local Miniconda
if exist "%DEFAULT_MINICONDA_ROOT%\Scripts\conda.exe" (
    set "MINICONDA_ROOT=%DEFAULT_MINICONDA_ROOT%"
    call :report_conda_registry_status
    call :validate_conda_root
    if "!CONDA_VALID!"=="1" goto :found_local_conda
    echo [WARNING] Local Conda found but validation failed: %DEFAULT_MINICONDA_ROOT%
    set "MINICONDA_ROOT="
)
if /I not "%ALT_MINICONDA_ROOT%"=="%DEFAULT_MINICONDA_ROOT%" (
    if exist "%ALT_MINICONDA_ROOT%\Scripts\conda.exe" (
        set "MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
        call :report_conda_registry_status
        call :validate_conda_root
        if "!CONDA_VALID!"=="1" goto :found_local_conda
        echo [WARNING] Local Conda found but validation failed: %ALT_MINICONDA_ROOT%
        set "MINICONDA_ROOT="
    )
)
goto :install_conda

:found_local_conda
echo [OK] Local Miniconda is installed
echo Location: %MINICONDA_ROOT%
echo [OK] Conda validation passed
if exist "%MINICONDA_ROOT%\condabin\conda.bat" (
    set "PATH=%MINICONDA_ROOT%\condabin;%MINICONDA_ROOT%\Scripts;%PATH%"
)
call "%MINICONDA_ROOT%\Scripts\conda.exe" --version
goto :check_git

:install_conda

REM Need to install local Miniconda
echo [INFO] Local Miniconda not found
set "MINICONDA_ROOT=%DEFAULT_MINICONDA_ROOT%"
echo ========================================
echo.
echo This project needs Python 3.12
echo.

REM If the path is non-ASCII, warn and use a fallback path
if !PATH_HAS_CHINESE!==1 goto :__PATH_WARNING
goto :__PATH_WARNING_END

:__PATH_WARNING
echo ========================================
echo [WARNING] Path contains non-English characters
echo ========================================
echo Current path: %SCRIPT_DIR%
echo.
echo Miniconda has limited support for non-English paths
echo Using fallback install path: !MINICONDA_ROOT!
echo (same drive, different folder)
echo.
echo Tip: move the project to an ASCII-only path if you can
echo       Example: D:\manga-translator\
echo.
pause
echo.
goto :__PATH_WARNING_END

:__PATH_WARNING_END
echo.

echo Miniconda will be installed to: %MINICONDA_ROOT%
echo.
        echo Miniconda notes:
        echo   - Small download (about 50MB)
        echo   - Can manage multiple Python versions
        echo   - Isolated environments
        echo   - Includes pip
        echo.
echo Install Miniconda?
echo [1] Yes (recommended) - download and install
echo [2] No - install it yourself, then rerun this script
echo [3] Cancel
echo.
set /p install_conda="Choose (1/2/3, default 1): "

if "%install_conda%"=="2" (
    echo.
    echo Download Miniconda from:
    echo   Official: https://docs.conda.io/en/latest/miniconda.html
    echo   China mirror: https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/
    echo.
    echo Check "Add to PATH" during install
    echo Rerun this script after install
    pause
    exit /b 1
)

if "%install_conda%"=="3" (
    echo Install cancelled
    pause
    exit /b 1
)

REM Download and install Miniconda
echo.
echo Downloading Miniconda...
echo.

REM Miniconda download URL (Python 3.12)
set MINICONDA_OFFICIAL=https://repo.anaconda.com/miniconda/Miniconda3-py312_25.9.1-1-Windows-x86_64.exe
set MINICONDA_TUNA=https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py312_25.9.1-1-Windows-x86_64.exe

echo Choose a download source:
echo [1] Tsinghua mirror (faster in China)
echo [2] Anaconda official
echo.
set /p conda_source="Choose (1/2, default 1): "

if "%conda_source%"=="2" (
    set MINICONDA_URL=%MINICONDA_OFFICIAL%
    echo Using: Anaconda official
) else (
    set MINICONDA_URL=%MINICONDA_TUNA%
    echo Using: Tsinghua mirror
)

echo.
echo Downloading... (about 50MB, may take a few minutes)
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Write-Host 'Downloading Miniconda...'; try { Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile 'Miniconda3-latest.exe' -UseBasicParsing; Write-Host '[OK] Download complete'; exit 0 } catch { Write-Host '[ERROR] Download failed: $_'; exit 1 }}"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Download failed. Check your network connection
    echo.
    echo You can:
    echo 1. Download manually: %MINICONDA_URL%
    echo 2. Save as: Miniconda3-latest.exe
    echo 3. Put it in this folder and rerun the script
    pause
    exit /b 1
)

echo.
echo Installing Miniconda...
echo.
echo Install options:
echo   - Location: %MINICONDA_ROOT%
echo   - Python version: 3.12
echo   - For this project only
echo.
echo Installing silently...
timeout /t 2 >nul

        REM Silent Miniconda install
        start /wait Miniconda3-latest.exe /InstallationType=JustMe /AddToPath=1 /RegisterPython=0 /S /D=%MINICONDA_ROOT%

        if %ERRORLEVEL% neq 0 (
            echo.
            echo [ERROR] Miniconda install failed
            echo.
            pause
            exit /b 1
        )

        echo.
        echo [OK] Miniconda installed
        echo.

        REM Remove installer
        if exist "Miniconda3-latest.exe" (
            echo Removing installer...
            del /f /q "Miniconda3-latest.exe" >nul 2>&1
            if %ERRORLEVEL% == 0 (
                echo [OK] Installer removed
            )
        )
        echo.

        REM Initialize Conda
        echo Initializing Conda...
        call "%MINICONDA_ROOT%\Scripts\activate.bat"
        call conda init cmd.exe >nul 2>&1

        echo.
        echo [OK] Miniconda is installed and configured
        echo Install location: %MINICONDA_ROOT%
        echo.
        echo Close this window and run the script again
        echo (environment variables need to reload)
        pause
        exit /b 0

REM ===== Step 2: Check / download Git =====
:check_git
echo.
echo [2/5] Checking Git...
echo ========================================

REM Prefer local portable Git
if exist "%SCRIPT_DIR%\PortableGit\cmd\git.exe" (
    set "GIT=%SCRIPT_DIR%\PortableGit\cmd\git.exe"
    set "PATH=%SCRIPT_DIR%\PortableGit\cmd;%PATH%"
    echo [OK] Found local portable Git
    "%SCRIPT_DIR%\PortableGit\cmd\git.exe" --version
    goto :clone_repo
)

REM Check git on PATH
where git >nul 2>&1
if %ERRORLEVEL% == 0 (
    set GIT=git
    echo [OK] Found system Git
    git --version
    goto :clone_repo
)

echo [INFO] Git not found
echo.
echo Git is required to fetch the code. Choose:
echo [1] Download portable Git (recommended, about 50MB)
echo [2] Exit and install Git yourself
echo.
set /p git_choice="Choose (1/2): "

if "%git_choice%"=="2" (
    echo.
    echo Download: https://git-scm.com/downloads
    pause
    exit /b 0
)

if not "%git_choice%"=="1" (
    echo Invalid choice
    goto :check_git
)

REM Download Git
echo.
echo Downloading portable Git...
echo.
echo Choose a download source:
echo [1] GitHub official
echo [2] gh-proxy.com mirror (China)
echo.
set /p git_source="Choose (1/2, default 2): "

set GIT_VERSION=2.43.0
set GIT_ARCH=64-bit

if "%git_source%"=="1" (
    set GIT_URL=https://github.com/git-for-windows/git/releases/download/v%GIT_VERSION%.windows.1/PortableGit-%GIT_VERSION%-%GIT_ARCH%.7z.exe
    echo Using: GitHub official
) else (
    set GIT_URL=https://gh-proxy.com/https://github.com/git-for-windows/git/releases/download/v%GIT_VERSION%.windows.1/PortableGit-%GIT_VERSION%-%GIT_ARCH%.7z.exe
    echo Using: gh-proxy.com mirror
)

echo.
echo Downloading... (about 50MB, may take a few minutes)
if not exist "tmp" mkdir tmp
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Write-Host 'Downloading...'; try { Invoke-WebRequest -Uri '%GIT_URL%' -OutFile 'tmp\PortableGit.7z.exe' -UseBasicParsing; Write-Host '[OK] Download complete'; exit 0 } catch { Write-Host '[ERROR] Download failed: $_'; exit 1 }}"

if %ERRORLEVEL% neq 0 (
    echo.
    echo Download failed. Check your network and try again
    pause
    exit /b 1
)

echo.
echo Extracting Git...
tmp\PortableGit.7z.exe -o"PortableGit" -y >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Extract failed
    pause
    exit /b 1
)

del tmp\PortableGit.7z.exe >nul 2>&1
set GIT=PortableGit\cmd\git.exe
set "PATH=%CD%\PortableGit\cmd;%PATH%"
echo [OK] Git installed
PortableGit\cmd\git.exe --version

REM ===== Step 3: Clone / update repository =====
:clone_repo
echo.
echo [3/5] Checking the repository...
echo ========================================
echo.

REM Detect a zip extract (code exists, no .git)
if not exist ".git" (
    if exist "manga_translator" if exist "desktop_qt_ui" if exist "packaging\VERSION" (
        echo [INFO] Found project files extracted from a zip
        echo.
        echo Choose:
        echo [1] Skip Git and install dependencies (step 4 updates will not work)
        echo [2] Init Git and set origin (step 4 updates will work)
        echo [3] Exit
        echo.
        set /p zip_choice="Choose (1/2/3, default 2): "
        
        if "!zip_choice!"=="3" (
            exit /b 0
        ) else if "!zip_choice!"=="1" (
            echo [OK] Skipping Git; using existing files
            echo.
            goto :create_venv
        ) else (
            echo [INFO] Initializing Git repository...
            git init
            if !ERRORLEVEL! neq 0 (
                echo [ERROR] Git init failed
                pause
                exit /b 1
            )
            REM Get target repository URL
            call :get_repo_url
            echo.
            echo Adding remote origin...
            git remote add origin !REPO_URL!
            if !ERRORLEVEL! neq 0 (
                echo [ERROR] Failed to add remote
                pause
                exit /b 1
            )
            echo.
            echo Fetching remote branches...
            git fetch origin
            if !ERRORLEVEL! neq 0 (
                echo [WARNING] Fetch failed. This may be a network problem
                echo [INFO] Skipping Git; using existing files
                echo.
                goto :create_venv
            )
            echo.
            echo [OK] Git repository initialized
            echo [INFO] You can use step 4 to update later
            echo.
            goto :create_venv
        )
    )
)

REM Get the target repository URL first
call :get_repo_url

REM Check for an existing repository
if exist ".git" (
    echo [INFO] Existing Git repository found
    
    REM Read current remote URL
    for /f "delims=" %%i in ('"%GIT%" config --get remote.origin.url 2^>nul') do set CURRENT_REPO=%%i
    
    if defined CURRENT_REPO (
        echo Current remote: !CURRENT_REPO!
        echo Target remote: !REPO_URL!
        echo.
        
        REM Normalize URLs before comparing
        set CURRENT_CLEAN=!CURRENT_REPO:.git=!
        set TARGET_CLEAN=!REPO_URL:.git=!
        
        REM Strip common mirror prefixes to github.com
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://gh-proxy.com/https://github.com/=https://github.com/!
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://ghproxy.com/https://github.com/=https://github.com/!
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://mirror.ghproxy.com/https://github.com/=https://github.com/!
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://ghfast.top/https://github.com/=https://github.com/!
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://gitproxy.click/https://github.com/=https://github.com/!
        set CURRENT_CLEAN=!CURRENT_CLEAN:https://gitee.com/hgmzhn/=https://github.com/hgmzhn/!

        set TARGET_CLEAN=!TARGET_CLEAN:https://gh-proxy.com/https://github.com/=https://github.com/!
        set TARGET_CLEAN=!TARGET_CLEAN:https://ghproxy.com/https://github.com/=https://github.com/!
        set TARGET_CLEAN=!TARGET_CLEAN:https://mirror.ghproxy.com/https://github.com/=https://github.com/!
        set TARGET_CLEAN=!TARGET_CLEAN:https://ghfast.top/https://github.com/=https://github.com/!
        set TARGET_CLEAN=!TARGET_CLEAN:https://gitproxy.click/https://github.com/=https://github.com/!
        set TARGET_CLEAN=!TARGET_CLEAN:https://gitee.com/hgmzhn/=https://github.com/hgmzhn/!
        
        if "!CURRENT_CLEAN!"=="!TARGET_CLEAN!" (
            echo [OK] Remote matches. Syncing to the latest version...
            echo.
            
            echo Fetching remote updates...
            "%GIT%" fetch origin
            if !ERRORLEVEL! neq 0 (
                echo [WARNING] Fetch failed. This may be a network problem
                echo.
                echo Choose:
                echo [1] Retry
                echo [2] Exit
                echo.
                set /p network_choice="Choose (1/2, default 1): "
                
                if "!network_choice!"=="2" goto :install_cancelled
                echo [INFO] Retrying fetch...
                goto :clone_repo
            )
                echo Hard-reset to origin/main...
                "%GIT%" reset --hard origin/main
                if !ERRORLEVEL! == 0 (
                    echo [OK] Code updated to the latest version
                    echo.
                    echo Removing leftover macOS helper scripts...
                    if exist "macOS_1_首次安装.sh" del /f /q "macOS_1_首次安装.sh" >nul 2>&1
                    if exist "macOS_2_启动Qt界面.sh" del /f /q "macOS_2_启动Qt界面.sh" >nul 2>&1
                    if exist "macOS_3_检查更新并启动.sh" del /f /q "macOS_3_检查更新并启动.sh" >nul 2>&1
                    if exist "macOS_4_更新维护.sh" del /f /q "macOS_4_更新维护.sh" >nul 2>&1
                    if exist "macOS_common.sh" del /f /q "macOS_common.sh" >nul 2>&1
                    echo [OK] Leftover macOS helper scripts removed
                    echo.
                    goto :create_venv
                ) else (
                    echo [WARNING] Sync failed, trying the main branch...
                    "%GIT%" checkout -f main
                    "%GIT%" reset --hard origin/main
                    if !ERRORLEVEL! == 0 (
                        echo [OK] Code updated to the latest version
                        echo.
                        echo Removing leftover macOS helper scripts...
                        if exist "macOS_1_首次安装.sh" del /f /q "macOS_1_首次安装.sh" >nul 2>&1
                        if exist "macOS_2_启动Qt界面.sh" del /f /q "macOS_2_启动Qt界面.sh" >nul 2>&1
                        if exist "macOS_3_检查更新并启动.sh" del /f /q "macOS_3_检查更新并启动.sh" >nul 2>&1
                        if exist "macOS_4_更新维护.sh" del /f /q "macOS_4_更新维护.sh" >nul 2>&1
                        if exist "macOS_common.sh" del /f /q "macOS_common.sh" >nul 2>&1
                        echo [OK] Leftover macOS helper scripts removed
                        echo.
                        goto :create_venv
                    ) else (
                        echo [WARNING] Sync failed
                        echo.
                        echo Choose:
                        echo [1] Retry
                        echo [2] Exit
                        echo.
                        set /p sync_choice="Choose (1/2, default 1): "
                        
                        if "!sync_choice!"=="2" goto :install_cancelled
                        echo [INFO] Retrying sync...
                        goto :clone_repo
                    )
                )
            )
        ) else (
            echo [WARNING] Remote URL does not match. Files will be deleted and cloned again
            echo Current remote: !CURRENT_REPO!
            echo Target remote: !REPO_URL!
            echo.
        )
    ) else (
        echo [WARNING] Could not read remote info. Files will be deleted and cloned again
        echo.
    )
    
    REM Confirm before cleanup
    echo ========================================
    echo WARNING: files in this folder will be deleted
    echo ========================================
    echo.
    echo ========================================
    echo   DANGER: only this folder will be deleted
    echo ========================================
    echo.
    echo Delete scope:
    echo   Current folder: %SCRIPT_DIR%
    echo   Only extra files in this folder will be deleted
    echo   Nothing outside this folder will be deleted
    echo.
    echo Keep:
    echo   - venv / conda_env (Python env)
    echo   - PortableGit
    echo   - Miniconda3
    echo   - this installer (step1-first-install.bat)
    echo.
    echo ========================================
    echo   All other files in this folder will be permanently deleted
    echo ========================================
    echo.
    echo Continue?
    echo [1] Yes - delete and clone again
    echo [2] No - cancel (back up important files first)
    echo.
    set /p confirm_delete="Choose (1/2, default 2): "
    
    if not "!confirm_delete!"=="1" (
        echo.
        echo Install cancelled
        pause
        exit /b 1
    )
    
:delete_and_clone
    REM Delete old files (keep venv, PortableGit, Python-3.12.12, Portable7z, Miniconda3, conda_env)
    echo.
    echo Cleaning old files...
    
    REM Delete folders (keep venv, conda_env, PortableGit, Python-3.12.12, Portable7z, Miniconda3)
    for /d %%d in (*) do (
        if /i not "%%d"=="venv" if /i not "%%d"=="conda_env" if /i not "%%d"=="PortableGit" if /i not "%%d"=="Python-3.12.12" if /i not "%%d"=="Portable7z" if /i not "%%d"=="Miniconda3" (
            echo Deleting folder: %%d
            rmdir /s /q "%%d" 2>nul
        )
    )
    
    REM Delete files (keep this script)
    for %%f in (*) do (
        if /i not "%%~nxf"=="%~nx0" (
            echo Deleting file: %%~nxf
            del /f /q "%%f" 2>nul
        )
    )
    
    REM Delete hidden .git folder
    if exist ".git" (
        echo Deleting .git ...
        rmdir /s /q ".git" 2>nul
        if exist ".git" (
            echo [ERROR] Could not delete .git; it may be in use
            echo Close related programs and try again
            pause
            exit /b 1
        )
    )
    
    echo [OK] Old files removed
    echo.
)

echo Repository URL: !REPO_URL!
echo Install folder: %SCRIPT_DIR%
echo.
goto :do_clone

:get_repo_url
echo Choose a clone source:
echo [1] GitHub official
echo [2] Gitee mirror (China)
echo [3] Enter a custom repository URL
echo.
set /p repo_choice="Choose (1/2/3, default 2): "

if "%repo_choice%"=="1" (
    set REPO_URL=https://github.com/hgmzhn/manga-translator-ui.git
    echo Using: GitHub official
) else if "%repo_choice%"=="3" (
    set /p REPO_URL="Enter repository URL: "
    echo Using: custom URL
) else (
    set REPO_URL=https://gitee.com/hgmzhn/manga-translator-ui.git
    echo Using: Gitee mirror
)
echo.
goto :eof

:do_clone

REM Clone into a temporary folder
set TEMP_DIR=manga_translator_temp_%RANDOM%
echo Cloning into a temporary folder... (may take a few minutes)
echo.
"%GIT%" clone !REPO_URL! %TEMP_DIR%

echo.
echo [DEBUG] Checking clone result...
if exist "%TEMP_DIR%" (
    if exist "%TEMP_DIR%\.git" (
        goto :copy_files
    )
)

REM Clone failed if we reach this point
echo.
echo [ERROR] Clone failed
echo.
echo Possible causes:
echo 1. Network problem
echo 2. Wrong repository URL
echo 3. GitHub access blocked (try the Gitee mirror)
echo.
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
set /p retry="Retry? (y/n): "
if /i "!retry!"=="y" goto :clone_repo
pause
exit /b 1

:copy_files

echo.
echo Copying files...

echo Copying folders...
for /d %%i in ("%TEMP_DIR%\*") do (
    if /i not "%%~nxi"=="PortableGit" (
        xcopy "%%i" "%SCRIPT_DIR%\%%~nxi\" /E /H /Y /I /Q
        if !ERRORLEVEL! neq 0 echo [ERROR] Failed to copy folder: %%~nxi
    )
)

echo.
echo Copying files...
for %%i in ("%TEMP_DIR%\*") do (
    if /i not "%%~nxi"=="%~nx0" (
        copy /Y "%%i" "%SCRIPT_DIR%\" >nul
        if !ERRORLEVEL! neq 0 echo [ERROR] Failed to copy file: %%~nxi
    )
)

echo.
echo Copying hidden files...
if exist "%TEMP_DIR%\.git\" (
    xcopy "%TEMP_DIR%\.git" ".git\" /E /H /Y /I /Q
    if !ERRORLEVEL! neq 0 echo [ERROR] Failed to copy .git
)

    copy /Y "%TEMP_DIR%\.gitignore" . >nul
    if !ERRORLEVEL! neq 0 echo [ERROR] Failed to copy .gitignore
)

echo.
echo Removing leftover macOS helper scripts...
if exist "macOS_1_首次安装.sh" del /f /q "macOS_1_首次安装.sh" >nul 2>&1
if exist "macOS_2_启动Qt界面.sh" del /f /q "macOS_2_启动Qt界面.sh" >nul 2>&1
if exist "macOS_3_检查更新并启动.sh" del /f /q "macOS_3_检查更新并启动.sh" >nul 2>&1
if exist "macOS_4_更新维护.sh" del /f /q "macOS_4_更新维护.sh" >nul 2>&1
if exist "macOS_common.sh" del /f /q "macOS_common.sh" >nul 2>&1
echo [OK] Leftover macOS helper scripts removed

echo.
echo Removing temporary folder...
rmdir /s /q "%TEMP_DIR%"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to remove temporary folder
)

echo.
echo [OK] Clone complete

:create_venv

REM ===== Step 4: Create Conda env and install dependencies =====
echo.
echo.
echo ========================================
echo [4/5] Creating Python environment and installing dependencies...
echo ========================================
echo.

REM Re-detect Conda path
if not defined DEFAULT_MINICONDA_ROOT (
    set "DEFAULT_MINICONDA_ROOT=%SCRIPT_DIR%\Miniconda3"
    set "ALT_MINICONDA_ROOT=%~d0\Miniconda3"
    REM Detect non-ASCII path characters
    powershell -Command "$path = '%SCRIPT_DIR%'; if ($path -match '[^\x00-\x7F]') { exit 1 } else { exit 0 }" >nul 2>&1
    if errorlevel 1 (
        set "DEFAULT_MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
    )
)

if not defined MINICONDA_ROOT (
    if exist "%DEFAULT_MINICONDA_ROOT%\Scripts\conda.exe" (
        set "MINICONDA_ROOT=%DEFAULT_MINICONDA_ROOT%"
    )
)
if not defined MINICONDA_ROOT (
    if /I not "%ALT_MINICONDA_ROOT%"=="%DEFAULT_MINICONDA_ROOT%" (
        if exist "%ALT_MINICONDA_ROOT%\Scripts\conda.exe" (
            set "MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
        )
    )
)
if not defined MINICONDA_ROOT (
    if defined CONDA_EXE (
        for /f "delims=" %%i in ('"%CONDA_EXE%" info --base 2^>nul') do (
            if exist "%%i\Scripts\conda.exe" set "MINICONDA_ROOT=%%i"
        )
    )
)
if not defined MINICONDA_ROOT (
    for /f "delims=" %%i in ('conda info --base 2^>nul') do (
        if exist "%%i\Scripts\conda.exe" set "MINICONDA_ROOT=%%i"
    )
)
if not defined MINICONDA_ROOT (
    for /f "delims=" %%i in ('where conda 2^>nul') do (
        if not defined MINICONDA_ROOT (
            if /I "%%~nxi"=="conda.exe" (
                for %%p in ("%%~dpi..") do if exist "%%~fp\Scripts\conda.exe" set "MINICONDA_ROOT=%%~fp"
            ) else if /I "%%~nxi"=="conda.bat" (
                for %%p in ("%%~dpi..") do if exist "%%~fp\Scripts\conda.exe" set "MINICONDA_ROOT=%%~fp"
            )
        )
    )
)

REM Initialize Conda so the conda command works
echo Initializing Conda...
if exist "%MINICONDA_ROOT%\condabin\conda.bat" (
    set "PATH=%MINICONDA_ROOT%\condabin;%MINICONDA_ROOT%\Scripts;%PATH%"
    echo [OK] Conda initialized
    echo Location: %MINICONDA_ROOT%
) else if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
    call "%MINICONDA_ROOT%\Scripts\activate.bat"
    echo [OK] Conda initialized
    echo Location: %MINICONDA_ROOT%
) else (
    REM Fall back to system Conda
    where conda >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Conda not found
        echo Make sure Conda is installed
        echo.
        echo Expected location: %MINICONDA_ROOT%
        pause
        exit /b 1
    )
    echo [OK] Using system Conda
)
echo.

REM Use a named environment (avoids non-ASCII path issues)
set CONDA_ENV_NAME=manga-env
set CONDA_ENV_EXISTS=0
set "CONDA_BASE="
set "ENV_PATH="
set "ENV_PYTHON="
set "USE_DIRECT_ENV_PYTHON=0"

REM Accept Conda TOS in advance to avoid interactive prompts
call conda config --set channel_priority flexible >nul 2>&1
call conda tos accept >nul 2>&1

REM Check whether the env exists via conda info --envs
echo Checking environment...
REM Use /B to match the env name at the start of the line
call conda info --envs 2>nul | findstr /B /C:"%CONDA_ENV_NAME%" >nul 2>nul
if %ERRORLEVEL% == 0 goto :env_exists
REM Environment missing; create a new one
echo [INFO] Environment not found; creating a new one
goto :create_new_env

:env_exists
set CONDA_ENV_EXISTS=1
echo [OK] Existing Conda environment: %CONDA_ENV_NAME%
echo.
echo Existing Conda environment found. Recreate it?
echo [1] Use existing environment (faster)
echo [2] Recreate environment (clean install)
echo.
set /p recreate_env="Choose (1/2, default 1): "

if "!recreate_env!"=="2" goto :delete_and_recreate

REM User chose the existing environment
echo.
echo [OK] Using existing environment
goto :activate_env

:delete_and_recreate
echo.
echo Removing existing environment...
call conda deactivate >nul 2>&1
call conda env remove -n "%CONDA_ENV_NAME%" -y >nul 2>&1
set CONDA_ENV_EXISTS=0
echo [OK] Environment removed
echo.
REM Create a new environment after delete

REM Create new environment
:create_new_env
echo.
echo [INFO] Creating Conda environment...
echo Environment name: %CONDA_ENV_NAME%
echo Python version: 3.12
echo.

REM Remove stale env registration
echo Cleaning Conda env list...
call conda env remove -n "%CONDA_ENV_NAME%" -y >nul 2>&1

REM Remove a leftover env folder that was never registered
REM Get Conda envs folder
for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
if not defined CONDA_BASE set "CONDA_BASE=%MINICONDA_ROOT%"
if exist "%CONDA_BASE%\envs\%CONDA_ENV_NAME%" (
    echo Found an unregistered env folder, removing it...
    rmdir /s /q "%CONDA_BASE%\envs\%CONDA_ENV_NAME%" 2>nul
)

REM Accept Conda TOS
call conda config --set channel_priority flexible >nul 2>&1
call conda tos accept >nul 2>&1

REM Clean possibly corrupted package cache
echo Cleaning package cache...
call conda clean --all -y >nul 2>&1

REM Create named environment
echo Creating environment: %CONDA_ENV_NAME%
call conda create -n "%CONDA_ENV_NAME%" python=3.12.* -y
if !ERRORLEVEL! neq 0 goto :create_env_failed
echo [OK] Conda environment created
goto :activate_env

:create_env_failed
echo.
echo [ERROR] Failed to create Conda environment
echo.
echo This may be a channel or cache problem
echo.
echo Try automatic repair?
echo [1] Yes - reset channels and retry
echo [2] No - exit installer
echo.
set /p fix_choice="Choose (1/2, default 1): "

if "!fix_choice!"=="2" (
    echo Install cancelled
    pause
    exit /b 1
)

echo.
echo Trying repair...
echo 1. Resetting channels...
call conda config --remove-key channels >nul 2>&1
echo 2. Clearing index cache...
call conda clean --index-cache -y >nul 2>&1
echo 3. Retrying environment create...
echo.
call conda create -n "%CONDA_ENV_NAME%" python=3.12.* -y
if !ERRORLEVEL! neq 0 goto :create_env_failed_final

echo [OK] Repair succeeded
goto :activate_env

:create_env_failed_final
echo [ERROR] Repair failed; environment still could not be created
echo.
echo Possible fixes:
echo 1. Run: conda update -n base conda
echo 2. Reinstall Miniconda
pause
exit /b 1

:activate_env
echo.
echo Activating environment...

call :resolve_env_path_s1
if not defined ENV_PATH goto :activate_failed_s1
if not exist "!ENV_PATH!\python.exe" goto :activate_failed_s1
set "ENV_PYTHON=!ENV_PATH!\python.exe"
set "USE_DIRECT_ENV_PYTHON=0"

REM Method 1: conda activate
call conda activate "%CONDA_ENV_NAME%" 2>nul && (
    echo [OK] Activated named environment: %CONDA_ENV_NAME%
    goto :env_activated
)

REM Method 2: activate.bat
echo [INFO] Trying fallback activation...
if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
    call "%MINICONDA_ROOT%\Scripts\activate.bat" "%CONDA_ENV_NAME%" 2>nul && (
        echo [OK] Activated named environment: %CONDA_ENV_NAME%
        goto :env_activated
    )
)

REM Fallback: call env Python directly without aborting
echo [WARNING] Activation failed; calling env Python directly
echo [INFO] Environment path: !ENV_PATH!
set "USE_DIRECT_ENV_PYTHON=1"
set "CONDA_PREFIX=!ENV_PATH!"
set "CONDA_DEFAULT_ENV=%CONDA_ENV_NAME%"
goto :env_activated

:activate_failed_s1
REM Could not resolve env path; the environment is incomplete
echo.
echo [WARNING] Could not locate environment: %CONDA_ENV_NAME%
echo.
echo Possible causes:
echo   1. Environment was not created completely
echo   2. Conda env list is invalid
echo.
echo Choose:
echo [1] Recreate environment (delete the existing one)
echo [2] Exit and fix it manually
echo.
set /p activate_choice="Choose (1/2): "
if "!activate_choice!"=="2" goto :activate_exit_s1

echo.
echo Removing environment...
call conda deactivate >nul 2>&1
call conda env remove -n "%CONDA_ENV_NAME%" -y 2>nul

REM Check whether delete succeeded
call conda info --envs 2>nul | findstr /B /C:"%CONDA_ENV_NAME%" >nul 2>&1 && goto :delete_failed_s1

echo [OK] Environment removed
echo.
echo Recreating environment...
echo.
goto :create_new_env

:activate_exit_s1
echo.
echo Try:
echo   1. Close this window and open a new Command Prompt
echo   2. Run: conda init cmd.exe
echo   3. Run this script again
pause
exit /b 1

:delete_failed_s1
echo [ERROR] Could not remove the environment; it may be in use
echo Close related programs and try again
pause
exit /b 1

:resolve_env_path_s1
set "ENV_PATH="
if defined CONDA_BASE if exist "%CONDA_BASE%\envs\%CONDA_ENV_NAME%\python.exe" set "ENV_PATH=%CONDA_BASE%\envs\%CONDA_ENV_NAME%"
if not defined ENV_PATH (
    for /f "tokens=1,2,3" %%a in ('conda info --envs 2^>nul ^| findstr /B /C:"%CONDA_ENV_NAME%"') do (
        if "%%b"=="*" (
            set "ENV_PATH=%%c"
        ) else (
            set "ENV_PATH=%%b"
        )
    )
)
if not defined ENV_PATH if exist "%MINICONDA_ROOT%\envs\%CONDA_ENV_NAME%\python.exe" set "ENV_PATH=%MINICONDA_ROOT%\envs\%CONDA_ENV_NAME%"
exit /b 0

:run_env_python
if "%USE_DIRECT_ENV_PYTHON%"=="1" (
    call "!ENV_PYTHON!" %*
) else (
    call python %*
)
exit /b %ERRORLEVEL%

:env_activated

echo Upgrading pip...
call :run_env_python -m pip install --upgrade pip >nul 2>&1

echo Installing base packages...
call :run_env_python -m pip install packaging setuptools wheel >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARNING] Base package install failed, continuing...
)

echo Detecting GPU support...
echo.

REM Call launch.py to install dependencies
call :run_env_python packaging\launch.py --install-deps-only

if !ERRORLEVEL! neq 0 (
    echo.
    echo [ERROR] Dependency install failed
    echo.
    echo You can run this later:
    echo   step4-maintenance.bat
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Dependencies installed

REM ===== Step 5: Done =====
echo.
echo [5/5] Install complete
echo ========================================
echo.
echo [OK] All steps finished
echo.
echo Install location: %SCRIPT_DIR%
echo.
echo Next:
echo   Double-click step2-launch-qt.bat to launch
echo   or step3-update-and-launch.bat (check for updates first)
echo.
echo To update later:
echo   Double-click step4-maintenance.bat
echo.
pause

REM Ask about pip cache cleanup
echo.
echo ========================================
echo Disk cleanup
echo ========================================
echo.
echo pip cache can use a lot of disk space
echo Clearing the cache does not uninstall packages
echo.
set /p clean_cache="Clear pip cache? (y/n, default n): "
if /i "%clean_cache%"=="y" (
    echo.
    echo Clearing pip cache...
    call :run_env_python -m pip cache purge >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Cache cleanup failed (permissions?)
    ) else (
        echo [OK] Cache cleared
    )
) else (
    echo [INFO] Skipped cache cleanup
)

REM Ask whether to launch now
echo.
set /p run_now="Launch now? (y/n): "
if /i "%run_now%"=="y" (
    echo.
    echo Launching...
    start step2-launch-qt.bat
)

echo.
echo Installer finished
pause
goto :eof

:detect_conda_registry
set "CONDA_REGISTRY_FOUND=0"
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" /f "Miniconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall" /f "Miniconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall" /f "Miniconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" /f "Anaconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall" /f "Anaconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall" /f "Anaconda" /s >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKCU\Software\Microsoft\Command Processor" /v AutoRun 2>nul | findstr /I "conda" >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
if "!CONDA_REGISTRY_FOUND!"=="0" reg query "HKLM\Software\Microsoft\Command Processor" /v AutoRun 2>nul | findstr /I "conda" >nul 2>&1 && set "CONDA_REGISTRY_FOUND=1"
goto :eof

:report_conda_registry_status
if "!CONDA_REGISTRY_FOUND!"=="1" (
    echo [INFO] Found Conda uninstall registry info
) else (
    if defined MINICONDA_ROOT (
        echo [INFO] No registry info, but a usable Conda was found
    ) else (
        echo [INFO] No Conda registry info found
    )
)
goto :eof

:validate_conda_root
set "CONDA_VALID=0"
set "CONDA_VALID_BASE="
if not defined MINICONDA_ROOT goto :eof
if exist "%MINICONDA_ROOT%\condabin\conda.bat" (
    set "PATH=%MINICONDA_ROOT%\condabin;%MINICONDA_ROOT%\Scripts;%PATH%"
) else if exist "%MINICONDA_ROOT%\Scripts\conda.exe" (
    set "PATH=%MINICONDA_ROOT%\Scripts;%PATH%"
) else (
    goto :eof
)
if exist "%MINICONDA_ROOT%\Scripts\conda.exe" (
    call "%MINICONDA_ROOT%\Scripts\conda.exe" --version >nul 2>&1
    if errorlevel 1 goto :eof
    for /f "delims=" %%i in ('"%MINICONDA_ROOT%\Scripts\conda.exe" info --base 2^>nul') do set "CONDA_VALID_BASE=%%i"
) else (
    call conda --version >nul 2>&1
    if errorlevel 1 goto :eof
    for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_VALID_BASE=%%i"
)
if not defined CONDA_VALID_BASE goto :eof
if not exist "!CONDA_VALID_BASE!\Scripts\conda.exe" goto :eof
set "MINICONDA_ROOT=!CONDA_VALID_BASE!"
set "CONDA_VALID=1"
goto :eof

:install_cancelled
echo.
echo Install cancelled
pause
exit /b 1
