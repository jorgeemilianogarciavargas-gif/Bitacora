# Proyecto Bitacora 1.2

Aplicacion para registrar progreso personal, academico, habitos y deudas.

Incluye dos versiones:

- `index.html`: version movil/PWA para navegador y GitHub Pages.
- `bitacora.pyw`: version local de escritorio para Windows.

## Funciones

- Registro diario editable por fecha.
- Modo diario de tareas personalizadas.
- Apartado de ejercicio para planear que toca cada dia, rutina y duracion.
- Panel de los ultimos siete dias.
- Graficas de habitos, bienestar, avance academico y deudas.
- Historial completo de registros.
- Historial independiente de pagos, con multiples pagos por dia.
- Pago minimo, pago para no generar intereses y fecha limite por mes.
- Base de datos SQLite local.

## Uso en movil

Abre la version web publicada en GitHub Pages:

`https://jorgeemilianogarciavargas-gif.github.io/Bitacora/`

En Android/Chrome:

1. Abre el enlace.
2. Toca el menu de tres puntos.
3. Elige "Agregar a pantalla principal" o "Instalar app".

En iPhone/Safari:

1. Abre el enlace.
2. Toca Compartir.
3. Elige "Agregar a inicio".

Los datos moviles se guardan en el navegador de ese celular. Usa `Datos > Exportar JSON` para respaldarlos.

## Uso en Windows

- Windows.
- Python 3 con Tkinter incluido.

1. Descarga o clona este repositorio.
2. Ejecuta `iniciar_bitacora.bat`.
3. La base local se creara automaticamente en `datos/bitacora.db`.

## Privacidad

Este repositorio no incluye datos personales ni base de datos.

Los archivos generados localmente en `datos/` estan ignorados por Git. Para respaldar tu informacion de escritorio, copia manualmente `datos/bitacora.db` en un lugar seguro. Para respaldar la version movil, exporta el JSON desde la seccion `Datos`.

## Nota

Bitacora esta pensada como una herramienta personal ligera. No requiere internet y todos los datos se guardan localmente.
