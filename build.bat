@echo off
chcp 65001 >nul
echo 正在打包，请稍候...

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 未检测到 pyinstaller，正在安装...
    pip install pyinstaller
)

:: 先删除旧的 dist 文件夹
if exist dist rmdir /s /q dist

pyinstaller --noconfirm --onefile --console ^
    --name "KnightModder" ^
    --icon "assets/icon.ico" ^
    --add-data "assets;assets" ^
    --add-data "version.json;." ^
    main.py

echo.
echo 打包完成！正在测试运行...
echo.

:: 自动运行打包后的 exe，这样能看到报错
cd dist
KnightModder.exe
cd ..

echo.
pause