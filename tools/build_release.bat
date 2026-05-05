@echo off
rem -----------------------------------------------------------------
rem  Build the openQCM Q-1 standalone Windows release in one shot.
rem
rem  Usage (from the OPENQCM/ folder):
rem      tools\build_release.bat
rem
rem  Steps:
rem      1. Remove previous build/ and dist/ folders
rem      2. Run PyInstaller with the project spec
rem      3. Assemble the user-facing release bundle via package_release.py
rem
rem  Output:
rem      dist\openQCM_Q-1_release\          ready to zip and distribute
rem -----------------------------------------------------------------

setlocal
pushd "%~dp0\.."

echo === [1/3] Cleaning previous build artifacts ===
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"

echo.
echo === [2/3] Running PyInstaller ===
rem --log-level WARN suppresses the "Including X.dll" routine info noise.
rem For full diagnostic output, rerun manually as:
rem     pyinstaller --clean --log-level INFO openQCM_Q-1.spec
pyinstaller --clean --log-level WARN --noconfirm openQCM_Q-1.spec
if errorlevel 1 (
    echo.
    echo BUILD FAILED. See the PyInstaller output above.
    popd
    exit /b 1
)

echo.
echo === [3/3] Assembling release bundle ===
python tools\package_release.py
if errorlevel 1 (
    echo.
    echo PACKAGING FAILED. See the package_release.py output above.
    popd
    exit /b 1
)

echo.
echo === DONE ===
echo Release bundle: dist\openQCM_Q-1_release\
popd
endlocal
