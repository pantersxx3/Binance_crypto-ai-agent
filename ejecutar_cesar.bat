@echo off
echo ========================================
echo    TEST AUTOMATICO MULTI-MODELO
echo ========================================

:: Obtener lista de modelos disponibles
echo Obteniendo lista de modelos...
lms ls > temp_models.txt 2>nul

:: Filtrar solo los nombres de los modelos (quita líneas innecesarias)
for /f "tokens=1" %%a in ('findstr /r /c:"^[a-zA-Z0-9]" temp_models.txt') do (
    echo %%a >> models_list.txt
)

echo Modelos detectados:
type models_list.txt
echo.

:: Ejecutar backtest para cada modelo
for /f %%m in (models_list.txt) do (
    echo.
    echo ========================================
    echo Cargando modelo: %%m
    echo ========================================
    
    lms load %%m 2>nul
    
    echo Ejecutando backtest...
    python main.py --model "%%m" --mode backtest
    
    echo Descargando modelo...
    lms unload %%m 2>nul
    
    timeout /t 4 >nul
)

:: Limpieza
del temp_models.txt 2>nul
del models_list.txt 2>nul

echo.
echo ========================================
echo PRUEBA AUTOMATICA FINALIZADA
echo ========================================
pause