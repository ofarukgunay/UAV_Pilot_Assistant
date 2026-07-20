@echo off
chcp 65001 >nul
echo.
echo ================================================
echo   IHA Pilot Asistani - Hizli Baslatma
echo ================================================
echo.

:MENU
echo Nasil calistirmak istersiniz?
echo.
echo [1] Docker ile calistir     (Ollama localhost'ta kurulu olmali)
echo [2] Python ile calistir     (.venv ortamini kullanir)
echo [3] Sadece testleri calistir
echo [4] Cikis
echo.
set /p CHOICE=Seciminizi girin (1-4): 

if "%CHOICE%"=="1" goto DOCKER
if "%CHOICE%"=="2" goto PYTHON
if "%CHOICE%"=="3" goto TESTS
if "%CHOICE%"=="4" goto EXIT
echo Gecersiz secim. Tekrar deneyin.
goto MENU

:DOCKER
echo.
echo [Docker] Ollama kontrol ediliyor...
curl -s http://localhost:11434/ >nul 2>&1
if errorlevel 1 (
    echo [UYARI] Ollama localhost:11434 adresinde bulunamadi!
    echo Lutfen once 'ollama serve' komutunu calistirin.
    echo.
    pause
    goto MENU
)
echo [OK] Ollama calisiyor.
echo.
echo [Docker] Image olusturuluyor ve baslatiliyor...
echo Bu islem ilk seferinde 2-3 dakika surebilir.
echo.
docker compose up --build
goto END

:PYTHON
echo.
echo [Python] Sanal ortam kontrol ediliyor...
if not exist ".venv\Scripts\activate.bat" (
    echo [Bilgi] Sanal ortam bulunamadi, olusturuluyor...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [Bilgi] Bagimliliklar kuruluyor...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
echo.
echo [Ollama] Kontrol ediliyor...
curl -s http://localhost:11434/ >nul 2>&1
if errorlevel 1 (
    echo [UYARI] Ollama bulunamadi! Lutfen baska bir terminalde:
    echo         ollama serve
    echo komutunu calistirin, sonra bu pencereye donun.
    echo.
    pause
)
echo.
echo [Baslatiliyor] Web Dashboard: http://127.0.0.1:5000
python src/main.py --web
goto END

:TESTS
echo.
if not exist ".venv\Scripts\activate.bat" (
    echo [Hata] Once secim 2 ile Python kurulumu yapiniz.
    pause
    goto MENU
)
call .venv\Scripts\activate.bat
echo [Test] Tum testler calistiriliyor...
python -m pytest tests/ -v --tb=short
echo.
pause
goto MENU

:EXIT
echo Cikiliyor...
goto END

:END
echo.
