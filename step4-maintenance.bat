@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM Set PYTHONUTF8=1 to avoid conda encoding errors
set "PYTHONUTF8=1"

REM Fix %CD% becoming System32 when run as administrator
cd /d "%~dp0"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Check Conda env (named or path-based)
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

REM Detect non-ASCII characters in the path
set "TEMP_CHECK_PATH=%SCRIPT_DIR%"
powershell -Command "$path = '%TEMP_CHECK_PATH%'; if ($path -match '[^\x00-\x7F]') { exit 1 } else { exit 0 }" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    REM Non-ASCII path; use Miniconda at the drive root
    set "DEFAULT_MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
)

call :detect_conda_registry_s4

REM Prefer local Miniconda
if exist "%DEFAULT_MINICONDA_ROOT%\Scripts\conda.exe" (
    set "MINICONDA_ROOT=%DEFAULT_MINICONDA_ROOT%"
    echo [INFO] Local Miniconda: %MINICONDA_ROOT%
    goto :validate_detected_conda_s4
)
if /I not "%ALT_MINICONDA_ROOT%"=="%DEFAULT_MINICONDA_ROOT%" (
    if exist "%ALT_MINICONDA_ROOT%\Scripts\conda.exe" (
        set "MINICONDA_ROOT=%ALT_MINICONDA_ROOT%"
        echo [INFO] Local Miniconda: %MINICONDA_ROOT%
        goto :validate_detected_conda_s4
    )
)

REM Then check system Conda
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
    echo [ERROR] Conda not found
    echo Run step1-first-install.bat to install Miniconda first
    pause
    exit /b 1
)

:validate_detected_conda_s4
call :report_conda_registry_status_s4
call :validate_conda_root_s4
if "!CONDA_VALID!" neq "1" (
    echo [ERROR] Conda found but validation failed: %MINICONDA_ROOT%
    echo Run step1-first-install.bat to reinstall or repair Miniconda
    pause
    exit /b 1
)
echo [OK] Conda validation passed

:init_conda_cmd_s4
if exist "%MINICONDA_ROOT%\condabin\conda.bat" (
    set "PATH=%MINICONDA_ROOT%\condabin;%MINICONDA_ROOT%\Scripts;%PATH%"
) else if exist "%MINICONDA_ROOT%\Scripts\conda.exe" (
    set "PATH=%MINICONDA_ROOT%\Scripts;%PATH%"
)

:check_env_s4

REM Check whether the environment exists (named env first)
REM Use /B to match the env name at the start of the line
call conda info --envs 2>nul | findstr /B /C:"%CONDA_ENV_NAME%" >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [INFO] Named environment: %CONDA_ENV_NAME%
    set "CONDA_ENV_MODE=named"
    goto :env_check_ok_s4
)

REM Check legacy path-based environment
if exist "%CONDA_ENV_PATH%\python.exe" (
    echo [INFO] Found legacy path-based environment
    set "CONDA_ENV_MODE=legacy"
    goto :env_check_ok_s4
)

REM No environment found
echo [ERROR] Conda environment not found
echo Run step1-first-install.bat to create the environment first
pause
exit /b 1

:env_check_ok_s4

call :resolve_env_path_s4
if not defined ENV_PATH goto :activate_failed_s4
if not exist "!ENV_PATH!\python.exe" goto :activate_failed_s4
set "ENV_PYTHON=!ENV_PATH!\python.exe"
set "USE_DIRECT_ENV_PYTHON=0"

if /I "!CONDA_ENV_MODE!"=="named" (
    REM Method 1: activate named environment
    call conda activate "%CONDA_ENV_NAME%" 2>nul && goto :activated_ok_s4

    REM Method 2: activate.bat
    echo [INFO] Trying fallback activation...
    if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
        call "%MINICONDA_ROOT%\Scripts\activate.bat" "%CONDA_ENV_NAME%" 2>nul && goto :activated_ok_s4
    )
) else (
    REM Method 1: activate legacy path-based environment
    call conda activate "!ENV_PATH!" 2>nul && goto :activated_ok_s4

    REM Method 2: activate.bat with a path
    echo [INFO] Trying fallback activation...
    if exist "%MINICONDA_ROOT%\Scripts\activate.bat" (
        call "%MINICONDA_ROOT%\Scripts\activate.bat" "!ENV_PATH!" 2>nul && goto :activated_ok_s4
    )
)

echo [WARNING] Activation failed; calling env Python directly
echo [INFO] Environment path: !ENV_PATH!
call :apply_env_runtime_path_s4
set "USE_DIRECT_ENV_PYTHON=1"
set "CONDA_PREFIX=!ENV_PATH!"
if /I "!CONDA_ENV_MODE!"=="named" (
    set "CONDA_DEFAULT_ENV=%CONDA_ENV_NAME%"
) else (
    set "CONDA_DEFAULT_ENV=!ENV_PATH!"
)
goto :activated_ok_s4

:activate_failed_s4
echo [ERROR] Failed to activate environment
echo Open a new Command Prompt, run conda init cmd.exe, then retry
pause
exit /b 1

:resolve_env_path_s4
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

:apply_env_runtime_path_s4
set "PATH=!ENV_PATH!;!ENV_PATH!\Library\mingw-w64\bin;!ENV_PATH!\Library\usr\bin;!ENV_PATH!\Library\bin;!ENV_PATH!\Scripts;!ENV_PATH!\bin;%PATH%"
exit /b 0

:run_env_python_s4
if "%USE_DIRECT_ENV_PYTHON%"=="1" (
    call "!ENV_PYTHON!" %*
) else (
    call python %*
)
exit /b %ERRORLEVEL%

:activated_ok_s4

REM Add portable Git to PATH
if exist "%SCRIPT_DIR%\PortableGit\cmd\git.exe" set "PATH=%SCRIPT_DIR%\PortableGit\cmd;%PATH%"

REM Open the Python maintenance menu
call :run_env_python_s4 packaging\launch.py --maintenance
pause
goto :eof

:detect_conda_registry_s4
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

:report_conda_registry_status_s4
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

:validate_conda_root_s4
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
