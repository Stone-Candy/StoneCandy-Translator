@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM Set PYTHONUTF8=1 to avoid conda encoding errors
set "PYTHONUTF8=1"

REM Fix %CD% becoming system32 when running as administrator
REM Use the script's own directory as working directory
cd /d "%~dp0"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Check conda environment (supports both named and path-based environments)
set CONDA_ENV_NAME=manga-env
set CONDA_ENV_PATH=%SCRIPT_DIR%\conda_env
set "MINICONDA_ROOT="
set "DEFAULT_MINICONDA_ROOT=%SCRIPT_DIR%\Miniconda3"
set "ALT_MINICONDA_ROOT=%~d0\Miniconda3"
set "CONDA_REGISTRY_FOUND=0"
set "CONDA_VALID=0"
set "ENV_PATH="
set "ENV_PYTHON="
set "USE_DIRECT_ENV_PYTHON=0"
set "CONDA_ENV_MODE="

REM Detect if path contains non-ASCII characters (Chinese, etc.)
REM Use PowerShell for more reliable detection
set "TEMP_CHECK_PATH=%SCRIPT_DIR%"
powershell -Command "$path = '%TEMP_CHECK_PATH%'; if ($path -match '[^\x00-\x7F]') { exit 1 } else { exit 0 }" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    REM Path contains Chinese characters, use Miniconda at drive root
    set "DEFAULT_MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
)

call :detect_conda_registry_s2

REM Prioritize local Miniconda
if exist "%DEFAULT_MINICONDA_ROOT%\Scripts\conda.exe" (
    set "MINICONDA_ROOT=%DEFAULT_MINICONDA_ROOT%"
    echo [INFO] Detected local Miniconda: %MINICONDA_ROOT%
    goto :validate_detected_conda_s2
)
if /I not "%ALT_MINICONDA_ROOT%"=="%DEFAULT_MINICONDA_ROOT%" (
    if exist "%ALT_MINICONDA_ROOT%\Scripts\conda.exe" (
        set "MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
        echo [INFO] Detected local Miniconda: %MINICONDA_ROOT%
        goto :validate_detected_conda_s2
    )
)

REM Check system Conda
if defined CONDA_EXE (
    for /f "delims=" %%i in ('"%CONDA_EXE%" info --base 2^>nul') do (
        if exist "%%i\Scripts\conda.exe" set "MINICONDA_ROOT=%%i"
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

if not defined MINICONDA_ROOT (
    echo [ERROR] Conda not detected
    echo Please run step1-first-install.bat to install Miniconda first
    pause
    exit /b 1
)

:validate_detected_conda_s2
call :report_conda_registry_status_s2
call :validate_conda_root_s2
if "!CONDA_VALID!" neq "1" (
    echo [ERROR] Conda detected but validation failed: %MINICONDA_ROOT%
    echo Please run step1-first-install.bat to reinstall or repair Miniconda
    pause
    exit /b 1
)
echo [OK] Conda validation passed

:init_conda_cmd_s2
if exist "%MINICONDA_ROOT%\condabin\conda.bat" (
    set "PATH=%MINICONDA_ROOT%\condabin;%MINICONDA_ROOT%\Scripts;%PATH%"
) else if exist "%MINICONDA_ROOT%\Scripts\conda.exe" (
    set "PATH=%MINICONDA_ROOT%\Scripts;%PATH%"
)

:check_env_s2

REM Check if environment exists (prefer named environment)
REM Use /B option for exact prefix match to avoid false positives
call conda info --envs 2>nul | findstr /B /C:"%CONDA_ENV_NAME%" >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [INFO] Detected named environment: %CONDA_ENV_NAME%
    set "CONDA_ENV_MODE=named"
    goto :env_check_ok
)

REM Check legacy path-based environment
if exist "%CONDA_ENV_PATH%\python.exe" (
    echo [INFO] Detected legacy path-based environment
    set "CONDA_ENV_MODE=legacy"
    goto :env_check_ok
)

REM No environment found
echo [ERROR] Conda environment not detected
echo Please run step1-first-install.bat to create the environment
pause
exit /b 1

:env_check_ok

call :resolve_env_path_s2
if not defined ENV_PATH goto :activate_failed_s2
if not exist "!ENV_PATH!\python.exe" goto :activate_failed_s2
set "ENV_PYTHON=!ENV_PATH!\python.exe"
set "USE_DIRECT_ENV_PYTHON=0"

if /I "!CONDA_ENV_MODE!"=="named" (
    REM Method 1: Activate named environment
    call conda activate "%CONDA_ENV_NAME%" 2>nul && goto :activated_ok_s2

    REM Method 2: Use activate.bat for named environment
    echo [INFO] Trying fallback activation method...
    if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
        call "%MINICONDA_ROOT%\Scripts\activate.bat" "%CONDA_ENV_NAME%" 2>nul && goto :activated_ok_s2
    )
) else (
    REM Method 1: Activate legacy path-based environment
    call conda activate "!ENV_PATH!" 2>nul && goto :activated_ok_s2

    REM Method 2: Use activate.bat for legacy environment
    echo [INFO] Trying fallback activation method...
    if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
        call "%MINICONDA_ROOT%\Scripts\activate.bat" "!ENV_PATH!" 2>nul && goto :activated_ok_s2
    )
)

echo [WARNING] Environment activation failed, falling back to direct Python call
echo [INFO] Environment path: !ENV_PATH!
call :apply_env_runtime_path_s2
set "USE_DIRECT_ENV_PYTHON=1"
set "CONDA_PREFIX=!ENV_PATH!"
if /I "!CONDA_ENV_MODE!"=="named" (
    set "CONDA_DEFAULT_ENV=%CONDA_ENV_NAME%"
) else (
    set "CONDA_DEFAULT_ENV=!ENV_PATH!"
)
goto :activated_ok_s2

:activate_failed_s2
echo [ERROR] Failed to activate environment
echo Suggestion: Open a new Command Prompt, run "conda init cmd.exe", then try again
pause
exit /b 1

:resolve_env_path_s2
set "ENV_PATH="
if exist "%MINICONDA_ROOT%\envs\%CONDA_ENV_NAME%\python.exe" set "ENV_PATH=%MINICONDA_ROOT%\envs\%CONDA_ENV_NAME%"
if not defined ENV_PATH (
    for /f "tokens=1,2,3" %%a in ('conda info --envs 2^>nul ^| findstr /B /C:"%CONDA_ENV_NAME%"') do (
        if "%%b"=="*" (
            set "ENV_PATH=%%c"
        ) else (
            set "ENV_PATH=%%b"
        )
    )
)
if not defined ENV_PATH if exist "%CONDA_ENV_PATH%\python.exe" set "ENV_PATH=%CONDA_ENV_PATH%"
exit /b 0

:apply_env_runtime_path_s2
set "PATH=!ENV_PATH!;!ENV_PATH!\Library\mingw-w64\bin;!ENV_PATH!\Library\usr\bin;!ENV_PATH!\Library\bin;!ENV_PATH!\Scripts;!ENV_PATH!\bin;%PATH%"
exit /b 0

:run_env_python_s2
if "%USE_DIRECT_ENV_PYTHON%"=="1" (
    call "!ENV_PYTHON!" %*
) else (
    call python %*
)
exit /b %ERRORLEVEL%

:activated_ok_s2

REM Check for portable Git
if not exist "PortableGit\cmd\git.exe" goto :skip_git_s2
set "PATH=%SCRIPT_DIR%\PortableGit\cmd;%PATH%"
:skip_git_s2

REM Switch to project root directory (ensures Python can find modules correctly)
cd /d "%~dp0"

REM Launch Qt interface directly
call :run_env_python_s2 desktop_qt_ui\main.py

goto :eof

:detect_conda_registry_s2
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

:report_conda_registry_status_s2
if "!CONDA_REGISTRY_FOUND!"=="1" (
    echo [INFO] Registry installation info detected
) else (
    if defined MINICONDA_ROOT (
        echo [INFO] No registry info found, but usable Conda was detected
    ) else (
        echo [INFO] No registry installation info detected
    )
)
goto :eof

:validate_conda_root_s2
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
