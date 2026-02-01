@echo off
rem Save this file as "UTF-8 without BOM" if you see '' is not recognized
chcp 65001 >nul
setlocal EnableDelayedExpansion
:: SuperPicky - Windows 打包脚本（生成 exe 发布）
:: 参考 build_release.sh 实现
::
:: 用法:
::   build_release.bat           # 打包（默认）
::   build_release.bat --test    # 同默认，仅打包
::   build_release.bat --help    # 显示帮助

:: ============================================
:: 配置参数
:: ============================================
set "APP_NAME=SuperPicky"
set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

:: ============================================
:: 参数解析
:: ============================================
set "MODE=release"
if "%~1"=="--help" goto :show_help
if "%~1"=="-h" goto :show_help
if "%~1"=="--test" set "MODE=test"
goto :start

:show_help
echo SuperPicky Windows 构建脚本
echo.
echo 用法: %~nx0 [选项]
echo.
echo 选项:
echo   --test    仅打包（与默认相同，保留以便与 shell 脚本用法一致）
echo   --help    显示此帮助信息
echo.
echo 打包完成后，可执行文件位于: dist\SuperPicky\SuperPicky.exe
echo 可将整个 dist\SuperPicky 文件夹打包成 zip 发布。
echo.
exit /b 0

:start
:: ============================================
:: 步骤0: 环境检查
:: ============================================
echo.
echo [========================================]
echo 步骤0: 环境检查
echo [========================================]

:: 检查 Python
echo [INFO] 检查 Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请先安装 Python 并加入 PATH
    exit /b 1
)
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
echo [SUCCESS] Python: %PYTHON_EXE%

:: 检查 PyInstaller
echo [INFO] 检查 PyInstaller...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 PyInstaller，请先安装: pip install pyinstaller
    exit /b 1
)
echo [SUCCESS] PyInstaller 已就绪

:: 检查 spec 文件
if not exist "SuperPicky.spec" (
    echo [ERROR] 未找到 SuperPicky.spec 文件
    exit /b 1
)
echo [SUCCESS] SuperPicky.spec 已就绪

:: ============================================
:: 步骤1: 提取版本号
:: ============================================
echo.
echo [========================================]
echo 步骤1: 提取版本号
echo [========================================]

set "VERSION=0.0.0"
findstr /R "version = QLabel" ui\about_dialog.py > temp_ver.txt 2>nul
if exist temp_ver.txt (
    for /f "usebackq tokens=2 delims=^" %%a in ("temp_ver.txt") do set "VER_RAW=%%a" & set "VERSION=!VER_RAW:v=!"
    del temp_ver.txt 2>nul
)
if "%VERSION%"=="" (
    echo [WARNING] 无法从 ui\about_dialog.py 提取版本号，使用默认 0.0.0
    set "VERSION=0.0.0"
) else (
    echo [SUCCESS] 检测到版本: v%VERSION%
)

:: ============================================
:: 步骤1.5: 检测 CPU 架构
:: ============================================
echo [INFO] 检测 CPU 架构...
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set "ARCH_SUFFIX=x64"
    echo [SUCCESS] 检测到 x64 (AMD64)
) else if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set "ARCH_SUFFIX=arm64"
    echo [SUCCESS] 检测到 ARM64
) else if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    set "ARCH_SUFFIX=x86"
    echo [SUCCESS] 检测到 x86
) else (
    set "ARCH_SUFFIX=%PROCESSOR_ARCHITECTURE%"
    echo [WARNING] 未知架构: %PROCESSOR_ARCHITECTURE%
)

:: ============================================
:: 步骤2: 清理旧文件
:: ============================================
echo.
echo [========================================]
echo 步骤2: 清理旧文件
echo [========================================]

if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"
mkdir dist
echo [SUCCESS] 清理完成

:: ============================================
:: 步骤2.5: 注入构建信息（Git Commit Hash）
:: ============================================
echo.
echo [========================================]
echo 步骤2.5: 注入构建信息
echo [========================================]

set "COMMIT_HASH=unknown"
for /f "tokens=*" %%i in ('git rev-parse --short HEAD 2^>nul') do set "COMMIT_HASH=%%i"
echo [INFO] Commit Hash: %COMMIT_HASH%

set "BUILD_INFO_FILE=core\build_info.py"
set "BUILD_INFO_BACKUP=core\build_info.py.backup"
if exist "%BUILD_INFO_FILE%" copy /y "%BUILD_INFO_FILE%" "%BUILD_INFO_BACKUP%" >nul

:: 使用 PowerShell 替换 COMMIT_HASH 行
powershell -NoProfile -Command ^
    "(Get-Content -Path '%BUILD_INFO_FILE%' -Encoding UTF8) -replace 'COMMIT_HASH = .*', 'COMMIT_HASH = \"%COMMIT_HASH%\"' | Set-Content -Path '%BUILD_INFO_FILE%' -Encoding UTF8"
echo [SUCCESS] 构建信息已注入

:: ============================================
:: 步骤3: PyInstaller 打包
:: ============================================
echo.
echo [========================================]
echo 步骤3: PyInstaller 打包
echo [========================================]

echo [INFO] 正在打包应用（可能需要数分钟）...
python -m PyInstaller SuperPicky.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller 打包失败
    goto :restore_build_info
)

:: 恢复原始 build_info.py
:restore_build_info
if exist "%BUILD_INFO_BACKUP%" (
    move /y "%BUILD_INFO_BACKUP%" "%BUILD_INFO_FILE%" >nul
    echo [INFO] 已恢复原始 core\build_info.py
)

if errorlevel 1 exit /b 1

if not exist "dist\%APP_NAME%\SuperPicky.exe" (
    echo [ERROR] 打包失败！未找到 dist\%APP_NAME%\SuperPicky.exe
    exit /b 1
)
echo [SUCCESS] 打包完成

:: ============================================
:: 步骤4: 可选 - 创建发布用 zip
:: ============================================
echo.
echo [========================================]
echo 步骤4: 创建发布包
echo [========================================]

set "ZIP_NAME=%APP_NAME%_v%VERSION%_%ARCH_SUFFIX%.zip"
set "DIST_DIR=dist\%APP_NAME%"

:: 如已安装 7z 或 PowerShell 可用，则打 zip
where 7z >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 使用 7-Zip 创建 %ZIP_NAME% ...
    7z a -tzip "dist\%ZIP_NAME%" "dist\%APP_NAME%\*" -r >nul
    if not errorlevel 1 (
        echo [SUCCESS] 已创建: dist\%ZIP_NAME%
    )
) else (
    powershell -NoProfile -Command "if (Test-Path 'dist\%APP_NAME%') { Compress-Archive -Path 'dist\%APP_NAME%\*' -DestinationPath 'dist\%ZIP_NAME%' -Force; Write-Host '[SUCCESS] 已创建: dist\%ZIP_NAME%' } else { Write-Host '[INFO] 跳过 zip 创建' }"
)

:: ============================================
:: 完成报告
:: ============================================
echo.
echo [========================================]
echo 构建完成!
echo [========================================]
echo.
echo 可执行文件: dist\%APP_NAME%\SuperPicky.exe
echo 发布目录:   dist\%APP_NAME%\
echo 版本:       v%VERSION%
echo 架构:       %ARCH_SUFFIX%
echo.
echo 下一步:
echo   1. 测试 dist\%APP_NAME%\SuperPicky.exe
echo   2. 将 dist\%APP_NAME% 整个文件夹打包成 zip 分发给用户
echo   3. 或使用已生成的 dist\%ZIP_NAME% （若已创建）
echo.
echo [========================================]
exit /b 0
