@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║     IHA Pilot Asistani — Kurulum Scripti        ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo Bu script projeyi ilk kez kurmak icin calistirilir.
echo Yaklasik 1-2 dakika surebilir.
echo.

:: Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Lutfen https://python.org adresinden Python 3.10 veya ustunu kurun.
    echo Kurulum sirasinda "Add to PATH" secenegini isaretlemeyi unutmayin.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% bulundu.
echo.

:: Sanal ortam olustur
if exist ".venv\" (
    echo [Bilgi] Sanal ortam zaten mevcut, atlaniyor...
) else (
    echo [Kuruluyor] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam olusturulamadi!
        pause
        exit /b 1
    )
    echo [OK] Sanal ortam olusturuldu.
)
echo.

:: Bagimlilikları kur
echo [Kuruluyor] Python kutuphaneleri yukleniyor...
.venv\Scripts\pip.exe install -r requirements.txt --quiet
if errorlevel 1 (
    echo [HATA] Kutuphaneler yuklenemedi!
    echo Lutfen internet baglantinizi kontrol edin.
    pause
    exit /b 1
)
echo [OK] Tum kutuphaneler yuklendi.
echo.

:: .env dosyasını oluştur
if not exist ".env" (
    echo [Bilgi] .env dosyasi olusturuluyor...
    copy .env.example .env >nul
    echo [OK] .env dosyasi olusturuldu (varsayilan degerlerle^).
    echo.
    echo [DIKKAT] LLM icin Ollama gereklidir:
    echo    1. https://ollama.com adresinden Ollama yukleyin
    echo    2. Bir terminal acin ve: ollama pull llama3.2
    echo    3. Sonra run.bat ile projeyi baslatın
) else (
    echo [OK] .env dosyasi mevcut.
)
echo.

:: Testleri calistir
echo [Test] Kurulumu dogrulayan testler calistiriliyor...
.venv\Scripts\pytest.exe tests/ -q --tb=short 2>&1 | findstr /i "passed\|failed\|error"
echo.

echo ╔══════════════════════════════════════════════════╗
echo ║  Kurulum tamamlandi!                            ║
echo ║                                                  ║
echo ║  Projeyi baslatmak icin:                        ║
echo ║     run.bat  →  secim menusunden 2'yi secin     ║
echo ║                                                  ║
echo ║  Veya direkt:                                   ║
echo ║     .venv\Scripts\python.exe src/main.py --web  ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
