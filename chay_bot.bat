@echo off
REM ==============================================================================
REM QBot - BAT TUNG BOT tren Windows (moi bot 1 cua so CMD rieng)
REM
REM   chay_bot.bat                          -> xem danh sach bot
REM   chay_bot.bat hd_update_cho_va_khop    -> bat cho MOI tai khoan dang Bat
REM   chay_bot.bat hd_order_multi kh_a      -> chi tai khoan kh_a
REM
REM DUNG bot: bam Ctrl+C trong cua so cua bot do (hoac dong cua so).
REM Cua so giu nguyen khi bot loi de doc duoc thong bao loi.
REM ==============================================================================
chcp 65001 >nul
cd /d "%~dp0"
set "BOT=%~n1"
if "%BOT%"=="" goto :danh_sach
if not exist "%BOT%.py" (
    echo Khong co bot "%BOT%".
    echo.
    goto :danh_sach
)
if not exist "config.ini" (
    echo Khong tim thay config.ini
    exit /b 1
)

if "%~2"=="" (
    start "QBot - %BOT%" cmd /k "set QBOT_ACCOUNT=&& python %BOT%.py"
    echo Da mo cua so "QBot - %BOT%"  ^(moi tai khoan dang Bat^)
) else (
    start "QBot [%~2] - %BOT%" cmd /k "set QBOT_ACCOUNT=%~2&& python %BOT%.py"
    echo Da mo cua so "QBot [%~2] - %BOT%"
)
exit /b 0

:danh_sach
echo Cach dung: chay_bot.bat ^<ten_bot^> [tai_khoan]
echo.
echo   hd_update_cho_va_khop               Cho va khop - nguon cap SL/TP (bat TRUOC)
echo   hd_order_multi                      Dat lenh vao + SL/TP
echo   hd_alert_possition_and_open_order   Canh bao Telegram, don lenh khi vi the dong
echo   hd_cancel_selective                 Xoa lenh theo tick J-M
echo   hd_cancel_orders_schedule           Huy lenh vao treo qua lau
echo   hd_update_all                       So du -^> tab DAT LENH J1:M2
exit /b 1
