# Proyecto Bitacora 1.1

Aplicacion local de escritorio para registrar progreso personal, academico, habitos y deudas.

## Funciones

- Registro diario editable por fecha.
- Panel de los ultimos siete dias.
- Graficas de habitos, bienestar, avance academico y deudas.
- Historial completo de registros.
- Historial independiente de pagos, con multiples pagos por dia.
- Pago minimo y pago para no generar intereses por deuda.
- Base de datos SQLite local.

## Requisitos

- Windows.
- Python 3 con Tkinter incluido.

## Uso

1. Descarga o clona este repositorio.
2. Ejecuta `iniciar_bitacora.bat`.
3. La base local se creara automaticamente en `datos/bitacora.db`.

## Privacidad

Este repositorio no incluye datos personales ni base de datos.

Los archivos generados localmente en `datos/` estan ignorados por Git. Para respaldar tu informacion, copia manualmente `datos/bitacora.db` en un lugar seguro.

## Nota

Bitacora esta pensada como una herramienta personal ligera. No requiere internet y todos los datos se guardan localmente.
